from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import School, Staff, Student, Book, BookCopy, BookIssued, LibrarySetting, BookReservation


class TrusteeLibraryReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.trustee = User.objects.create_user(username='library-trustee', role='admin(trustee)')
        other_owner = User.objects.create_user(username='library-other', role='trustee')
        self.school = School.objects.create(name='Library school', code='library-report', login_id=self.trustee)
        self.other_school = School.objects.create(name='Other library', code='library-other', login_id=other_owner)
        self.trustee.school = self.school
        self.trustee.save()
        self.student = Student.objects.create(school=self.school, name='Reader', surname='Student', gr_no='GR-1')
        self.staff = Staff.objects.create(school=self.school, name='Teacher borrower', category='TEACHER')
        self.book = Book.objects.create(school=self.school, title='Science', author='Author', category='Reference', price='100', total_copies=5, available_copies=2)
        self.available = BookCopy.objects.create(school=self.school, book=self.book, accession_no='A-1', purchase_price='80')
        self.lost = BookCopy.objects.create(school=self.school, book=self.book, accession_no='A-2', status='LOST', purchase_price='90')
        self.damaged = BookCopy.objects.create(school=self.school, book=self.book, accession_no='A-3', status='DAMAGED', condition='MAJOR_DAMAGE')
        self.today = timezone.localdate()
        self.now = timezone.now()
        LibrarySetting.objects.create(school=self.school, grace_period_days=2, fine_per_day='3')
        self.student_loan = self.loan(student=self.student, issued_days=12, due_days=-5)
        self.staff_loan = self.loan(staff=self.staff, issued_days=4, due_days=-1)
        self.closed = self.loan(student=self.student, issued_days=20, due_days=-10, status='LOST', actual_return_date=self.now - timedelta(days=8), book_copy=self.lost, lost_fees='190', total_fine='190')
        BookReservation.objects.create(school=self.school, book=self.book, student=self.student)
        self.client = APIClient()
        self.client.force_authenticate(self.trustee)
        self.url = reverse('trustee-library-report')

    def loan(self, student=None, staff=None, issued_days=1, due_days=7, **kwargs):
        return BookIssued.objects.create(school=self.school, book=self.book, student=student, staff=staff,
            book_issued_date=self.now - timedelta(days=issued_days), due_date=self.now + timedelta(days=due_days), **kwargs)

    def report(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_totals_value_and_no_copy_double_count(self):
        data = self.report()
        current = data['current']
        self.assertEqual((current['total_titles'], current['total_copies'], current['registered_copies']), (1, 5, 3))
        self.assertEqual((current['issued'], current['student_issued'], current['staff_issued']), (2, 1, 1))
        self.assertEqual((current['overdue'], current['past_grace']), (2, 1))
        self.assertEqual((current['lost_copies'], current['damaged_copies']), (1, 1))
        self.assertEqual(current['stock_value'], '380.00')  # 80 + fallback 100 + 2 untracked x 100
        self.assertEqual(current['catalogue_value'], '500.00')
        self.assertEqual(current['waiting_reservations'], 1)
        self.assertEqual(data['period']['lost_loans'], 1)
        self.assertEqual(data['period']['assessed_fines'], '190.00')
        self.assertEqual(data['period']['estimated_late_fines'], '9.00')

    def test_student_staff_summaries_and_issue_dates(self):
        data = self.report()
        students = [row for row in data['borrowers'] if row['borrower_type'] == 'student']
        staff = [row for row in data['borrowers'] if row['borrower_type'] == 'staff']
        self.assertEqual((students[0]['total_loans'], students[0]['active'], students[0]['lost']), (2, 1, 1))
        self.assertEqual((staff[0]['total_loans'], staff[0]['overdue']), (1, 1))
        self.assertEqual(sum(day['total_issues'] for day in data['daily']), 3)
        filtered = self.report(from_date=str(self.today - timedelta(days=6)), borrower_type='staff', borrower=self.staff.pk)
        self.assertEqual(filtered['loans']['count'], 1)
        self.assertEqual(filtered['current']['issued'], 2)  # current headline is independent of loan filters

    def test_overdue_excludes_closed_loans_and_grace_is_separate(self):
        data = self.report(loan_status='OVERDUE')
        self.assertEqual(data['loans']['count'], 2)
        rows = {row['borrower_type']: row for row in data['loans']['results']}
        self.assertEqual(rows['student']['days_overdue'], 5)
        self.assertEqual(rows['student']['estimated_late_fine'], '9.00')
        self.assertEqual(rows['staff']['estimated_late_fine'], '0.00')

    def test_scope_and_read_only(self):
        other_student = Student.objects.create(school=self.other_school, name='Secret')
        other_book = Book.objects.create(school=self.other_school, title='Secret book', author='Other', category='Other')
        BookIssued.objects.create(school=self.other_school, book=other_book, student=other_student, book_issued_date=self.now, due_date=self.now)
        response = self.client.get(self.url, {'school': self.other_school.pk}, HTTP_X_SCHOOL_ID=str(self.other_school.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Secret', str(response.data))
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(self.url, {}, format='json').status_code, 405)

    def test_roles_and_school_required(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])
        for role in ['teacher', 'principal', 'librarian']:
            user = get_user_model().objects.create_user(username=f'report-{role}', role=role, school=self.school)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        user = get_user_model().objects.create_user(username='unassigned-library', role='trustee')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.trustee.is_active = False
        self.client.force_authenticate(self.trustee)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_owner_and_group_fallback(self):
        self.trustee.school = None
        self.trustee.role = ''
        self.trustee.save()
        group, _ = Group.objects.get_or_create(name='TRUSTEE')
        self.trustee.groups.add(group)
        self.assertEqual(self.report()['current']['total_titles'], 1)

    def test_invalid_filters(self):
        for filters in [{'from_date': 'bad'}, {'from_date': str(self.today), 'to_date': str(self.today - timedelta(days=1))}, {'to_date': str(self.today + timedelta(days=1))}, {'borrower': 1}, {'page': 0}, {'page_size': 101}, {'loan_status': 'wrong'}]:
            self.assertEqual(self.client.get(self.url, filters).status_code, 400)

    def test_pagination_and_empty_selection(self):
        first = self.report(page_size=1)
        second = self.report(page_size=1, page=2)
        self.assertEqual(first['loans']['count'], 3)
        self.assertNotEqual(first['loans']['results'][0]['id'], second['loans']['results'][0]['id'])
        empty = self.report(book=999999)
        self.assertEqual(empty['stocks'], [])
        self.assertEqual(empty['current']['stock_value'], '0.00')
        self.assertEqual(empty['loans']['count'], 0)

    def test_inactive_disposed_copies_excluded_from_retained_value(self):
        self.available.is_active = False
        self.available.save()
        self.damaged.status = 'DISPOSED'
        self.damaged.save()
        self.assertEqual(self.report()['current']['stock_value'], '200.00')

    def test_borrower_constraint(self):
        for kwargs in [{}, {'student': self.student, 'staff': self.staff}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.loan(**kwargs)

    @override_settings(MIGRATION_MODULES={})
    def test_migration_graph_and_staff_field(self):
        loader = MigrationLoader(None)
        self.assertNotIn('sms_app', loader.detect_conflicts())
        state = loader.project_state([('sms_app', '0054_library_staff_borrower')])
        model = state.apps.get_model('sms_app', 'BookIssued')
        self.assertTrue(model._meta.get_field('student').null)
        self.assertEqual(model._meta.get_field('staff').remote_field.model._meta.model_name, 'staff')
        self.assertIn('library_loan_exactly_one_borrower', [constraint.name for constraint in model._meta.constraints])


class LibraryStaffCirculationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        owner = User.objects.create_user(username='staff-library-owner', role='trustee')
        other_owner = User.objects.create_user(username='staff-library-other', role='trustee')
        self.school = School.objects.create(name='Staff library', code='staff-library', login_id=owner)
        self.other_school = School.objects.create(name='Staff library other', code='staff-library-other', login_id=other_owner)
        self.librarian = User.objects.create_user(username='librarian-tests', school=self.school)
        group, _ = Group.objects.get_or_create(name='LIBRARIAN')
        self.librarian.groups.add(group)
        Staff.objects.create(school=self.school, user=self.librarian, name='Librarian', category='LIBRARIAN')
        self.staff = Staff.objects.create(school=self.school, name='Staff borrower', category='TEACHER')
        self.student = Student.objects.create(school=self.school, name='Student borrower')
        self.book = Book.objects.create(school=self.school, title='Staff checkout', author='Author', category='Test', total_copies=3, available_copies=3)
        BookCopy.objects.create(school=self.school, book=self.book, accession_no='STAFF-1')
        self.client = APIClient()
        self.client.force_authenticate(self.librarian)
        self.url = '/api/book-issued/'

    def issue(self, **kwargs):
        return self.client.post(self.url, {'book': self.book.pk, **kwargs}, format='json')

    def test_staff_issue_renew_return_and_duplicate_guard(self):
        response = self.issue(staff=self.staff.pk)
        self.assertEqual(response.status_code, 201, response.data)
        pk = response.data['id']
        self.assertEqual(response.data['staff'], self.staff.pk)
        self.assertIsNone(response.data['student'])
        self.assertEqual(self.issue(staff=self.staff.pk).status_code, 400)
        self.assertEqual(self.client.post(f'{self.url}{pk}/renew/').status_code, 200)
        self.assertEqual(self.client.post(f'{self.url}{pk}/return/', {'condition': 'GOOD'}, format='json').status_code, 200)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 3)
        self.assertEqual(self.client.post(f'{self.url}{pk}/return/', {'condition': 'GOOD'}, format='json').status_code, 400)

    def test_student_checkout_still_works(self):
        response = self.issue(student=self.student.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['staff'])

    def test_invalid_and_external_borrowers_rejected(self):
        other = Staff.objects.create(school=self.other_school, name='Other staff')
        for payload in [{}, {'student': self.student.pk, 'staff': self.staff.pk}, {'staff': other.pk}]:
            self.assertEqual(self.issue(**payload).status_code, 400)
        self.staff.is_active = False
        self.staff.save()
        self.assertEqual(self.issue(staff=self.staff.pk).status_code, 400)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 3)

    def test_staff_lookup_scoped_and_loan_cannot_be_reassigned(self):
        other = Staff.objects.create(school=self.other_school, name='Other staff')
        response = self.client.get(f'{self.url}staff-borrowers/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(other.pk, [row['id'] for row in response.data])
        issue = self.issue(staff=self.staff.pk)
        self.assertEqual(issue.status_code, 201)
        self.assertEqual(self.client.patch(f'{self.url}{issue.data["id"]}/', {'staff': other.pk}, format='json').status_code, 400)

    def test_staff_lost_and_damaged_are_closed_and_reported(self):
        for condition in ['LOST', 'MAJOR_DAMAGE']:
            book = Book.objects.create(school=self.school, title=f'{condition} book', author='A', category='Test', price='50')
            BookCopy.objects.create(school=self.school, book=book, accession_no=condition)
            response = self.client.post(self.url, {'book': book.pk, 'staff': self.staff.pk}, format='json')
            self.assertEqual(response.status_code, 201, response.data)
            url = f'{self.url}{response.data["id"]}/return/'
            closed = self.client.post(url, {'condition': condition}, format='json')
            self.assertEqual(closed.status_code, 200)
            self.assertEqual(closed.data['status'], 'LOST' if condition == 'LOST' else 'DAMAGED')
            self.assertEqual(self.client.post(url, {'condition': condition}, format='json').status_code, 400)
