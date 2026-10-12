from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (School, Staff, Student, AcademicYear, SchoolClass, Division, AdmissionForm, Admission,
                     FormSection, FormField, StudentFieldValue, StudentExtraData, StudentAttendance,
                     FeeType, StudentFee, StudentFeePayment, Exam, Subject, Result, FinalStudentResult)


class TrusteeStudentReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.trustee = User.objects.create_user(username='students-trustee', role='admin(trustee)')
        other = User.objects.create_user(username='students-other', role='trustee')
        self.school = School.objects.create(name='Student report school', code='student-report', login_id=self.trustee)
        self.other_school = School.objects.create(name='Other student school', code='other-student-report', login_id=other)
        self.trustee.school = self.school
        self.trustee.save()
        self.year = AcademicYear.objects.create(school=self.school, name='2025-26', start_month=4, end_month=3)
        self.next_year = AcademicYear.objects.create(school=self.school, name='2026-27', start_month=4, end_month=3)
        self.class1 = SchoolClass.objects.create(school=self.school, school_class='Class 1')
        self.class2 = SchoolClass.objects.create(school=self.school, school_class='Class 2')
        self.division = Division.objects.create(school=self.school, SchoolClass=self.class1, division='A')
        self.form = AdmissionForm.objects.create(school=self.school, academic_year=self.year, title='Admissions')
        admission = Admission.objects.create(school=self.school, form=self.form, status='approved')
        self.a = Student.objects.create(school=self.school, name='First', surname='Reader', gr_no='G1', school_class=self.class1, division='A', academic_year=self.next_year, admission=admission, admission_date='2025-05-01')
        self.b = Student.objects.create(school=self.school, name='Second', gr_no='G2', school_class=self.class1, division='B', academic_year=self.year, is_active=False, admission_date='2024-05-01')
        self.c = Student.objects.create(school=self.school, name='Third', gr_no='G3', school_class=self.class2, division='A', academic_year=self.year, is_rte=True)
        self.section = FormSection.objects.create(school=self.school, form=self.form, title='Student information', order=1)
        self.field(self.a, 'Gender', 'Male')
        self.field(self.b, 'Gender', 'Female')
        self.field(self.b, 'Student status', 'Dropout')
        StudentExtraData.objects.create(student=self.a, scheduled_caste='SC')
        StudentExtraData.objects.create(student=self.c, leaving_date='2025-06-01')
        self.att(self.a, '2025-05-01', True, False)
        self.att(self.a, '2025-05-02', False, True)
        self.att(self.a, '2025-05-03', True, True)
        self.att(self.b, '2025-05-01', True, False)
        self.fee_type = FeeType.objects.create(school=self.school, name='Tuition', is_rte_applicable=True)
        self.fee = StudentFee.objects.create(school=self.school, academic_year=self.year, student=self.a, feetype=self.fee_type, amount='1000', discount_amount='100', fine_amount='50', due_date='2025-06-01')
        self.payment(self.fee, '200', 'cash')
        self.payment(self.fee, '300', 'cheque', is_verified=False)
        self.payment(self.fee, '100', 'cash', is_bounced=True)
        govt_type = FeeType.objects.create(school=self.school, name='RTE tuition', is_rte_applicable=False)
        self.govt = StudentFee.objects.create(school=self.school, academic_year=self.year, student=self.c, feetype=govt_type, amount='600')
        self.payment(self.govt, '200', 'govt_rte', payer_type='government')
        self.exam_staff = Staff.objects.create(school=self.school, name='Principal', category='PRINCIPAL')
        subject = Subject.objects.create(school=self.school, division=self.division, name='Maths')
        self.exam = Exam.objects.create(school=self.school, created_by=self.exam_staff, academic_year=self.year, title='Annual exam', subject=subject, exam_date='2025-05-05', start_time=time(9), end_time=time(10), class_group=self.class1, passing_marks='33', max_marks='100')
        Result.objects.create(exam=self.exam, student=self.a, marks_obtained='80', max_marks='100', status='VERIFIED')
        Result.objects.create(exam=self.exam, student=self.b, is_absent=True, max_marks='100', status='VERIFIED')
        Result.objects.create(exam=self.exam, student=self.c, marks_obtained='99', max_marks='100', status='DRAFT')
        FinalStudentResult.objects.create(school=self.school, academic_year=self.year, student=self.a, school_class=self.class1, total_percentage='90', grade='A', status='PUBLISHED', is_published=True)
        self.client = APIClient()
        self.client.force_authenticate(self.trustee)
        self.url = reverse('trustee-student-report')

    def field(self, student, label, value):
        field = FormField.objects.create(school=self.school, section=self.section, label=label, field_type='text', order=1)
        StudentFieldValue.objects.create(school=self.school, student=student, field=field, value=value)

    def att(self, student, day, present, absent):
        row = StudentAttendance.objects.create(school=self.school, student=student, is_present=present, is_absent=absent)
        StudentAttendance.objects.filter(pk=row.pk).update(attendance_date=day)

    def payment(self, fee, amount, mode, **kwargs):
        fee.refresh_from_db()
        return StudentFeePayment.objects.create(student_fee=fee, student=fee.student, feetype=fee.feetype, amount=amount, payment_mode=mode,
            payment_date=timezone.make_aware(datetime(2025, 5, 10, 12)), **kwargs)

    def report(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_totals_strength_gender_category_and_exits(self):
        report = self.report(academic_year=self.year.pk)
        summary = report['summary']
        self.assertEqual((summary['total_students'], summary['active'], summary['inactive']), (3, 2, 1))
        self.assertEqual((summary['new_admissions'], summary['dropouts'], summary['transferred'], summary['left_unspecified']), (1, 1, 0, 1))
        self.assertEqual({row['class_name']: row['total'] for row in report['class_strength']}, {'class 1': 2, 'class 2': 1})
        self.assertEqual(len(report['division_strength']), 3)
        self.assertEqual({row['label']: row['count'] for row in report['gender']}, {'Male': 1, 'Female': 1, 'Not recorded': 1})
        self.assertEqual(summary['category_missing'], 2)

    def test_attendance_denominator_and_missing_are_correct(self):
        report = self.report(academic_year=self.year.pk)
        self.assertEqual(report['summary']['attendance_percentage'], 66.67)
        self.assertEqual(report['summary']['unmarked_attendance'], 1)
        students = {row['id']: row for row in report['students']['results']}
        self.assertEqual(students[self.a.pk]['attendance_percentage'], 50)
        self.assertIsNone(students[self.c.pk]['attendance_percentage'])

    def test_fee_balances_receipts_and_rte_are_separate(self):
        report = self.report(academic_year=self.year.pk)
        summary = report['summary']
        self.assertEqual((summary['payable'], summary['credited_paid'], summary['pending']), ('950.00', '200.00', '750.00'))
        self.assertEqual((summary['student_collection'], summary['government_collection'], summary['govt_pending']), ('200.00', '200.00', '400.00'))
        dated = self.report(academic_year=self.year.pk, from_date='2025-06-01', to_date='2025-06-30')
        self.assertEqual(dated['summary']['student_collection'], '0.00')
        self.assertEqual(dated['summary']['pending'], '750.00')

    def test_cancelled_fees_are_excluded(self):
        StudentFee.objects.filter(pk=self.fee.pk).update(status='cancelled')
        summary = self.report(academic_year=self.year.pk)['summary']
        self.assertEqual((summary['payable'], summary['pending'], summary['student_collection']), ('0.00', '0.00', '0.00'))

    def test_verified_results_absent_and_published_finals(self):
        report = self.report(academic_year=self.year.pk)
        exam = report['exams'][0]
        self.assertEqual((exam['records'], exam['graded'], exam['passed'], exam['absent']), (2, 2, 1, 1))
        self.assertEqual((exam['average_percentage'], exam['pass_percentage']), (40, 50))
        self.assertEqual(report['summary']['published_final_average'], 90)
        self.assertEqual(report['result_record_count'], 2)
        self.assertNotIn('99', [row['marks_obtained'] for row in report['result_records']])

    def test_filters_search_and_pagination(self):
        self.assertEqual(self.report(school_class=self.class1.pk, division='A')['students']['count'], 1)
        self.assertEqual(self.report(search='First Reader')['students']['results'][0]['id'], self.a.pk)
        self.assertEqual(self.report(student_status='inactive')['students']['count'], 1)
        self.assertEqual(self.report(student_status='dropout')['students']['results'][0]['id'], self.b.pk)
        first, second = self.report(page_size=1), self.report(page_size=1, page=2)
        self.assertEqual(first['students']['count'], 3)
        self.assertNotEqual(first['students']['results'][0]['id'], second['students']['results'][0]['id'])

    def test_export_returns_every_matching_record(self):
        report = self.report(export_all='true', page_size=1)
        self.assertEqual(len(report['students']['results']), 3)
        self.assertEqual(len(report['fee_records']), 2)
        self.assertEqual(len(report['result_records']), 2)

    def test_detail_is_scoped_and_contains_fee_result_attendance(self):
        report = self.report(student=self.a.pk, academic_year=self.year.pk)
        self.assertEqual(report['students']['count'], 1)
        self.assertEqual(len(report['fee_records']), 1)
        self.assertEqual(len(report['result_records']), 1)
        self.assertEqual(len(report['attendance']), 3)
        other = Student.objects.create(school=self.other_school, name='Secret student')
        self.assertEqual(self.client.get(self.url, {'student': other.pk}).status_code, 404)

    def test_academic_year_trend_deduplicates_memberships(self):
        report = self.report(academic_year=self.year.pk)
        trends = {row['id']: row['recorded_students'] for row in report['enrollment_trends']}
        self.assertEqual(trends, {self.year.pk: 3, self.next_year.pk: 1})
        self.assertEqual(self.report(academic_year=self.next_year.pk)['students']['count'], 1)

    def test_school_scope_and_other_school_filters(self):
        other = Student.objects.create(school=self.other_school, name='Secret student')
        other_year = AcademicYear.objects.create(school=self.other_school, name='2025-26')
        response = self.client.get(self.url, HTTP_X_SCHOOL_ID=str(self.other_school.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(other.pk, [row['id'] for row in response.data['students']['results']])
        self.assertEqual(self.client.get(self.url, {'academic_year': other_year.pk}).status_code, 400)

    def test_roles_and_read_only(self):
        for role in ['principal', 'teacher', 'clerk', 'student']:
            user = get_user_model().objects.create_user(username=f'student-report-{role}', role=role, school=self.school)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])
        self.client.force_authenticate(self.trustee)
        self.assertEqual(self.client.post(self.url, {}).status_code, 405)
        self.assertEqual(self.client.patch(self.url, {}).status_code, 405)
        with patch.object(StudentFee, 'save', side_effect=AssertionError('Reports must not write fees')):
            self.report()

    def test_group_owner_and_no_school(self):
        self.trustee.school = None
        self.trustee.role = ''
        self.trustee.save()
        group, _ = Group.objects.get_or_create(name='TRUSTEE')
        self.trustee.groups.add(group)
        self.assertEqual(self.report()['summary']['total_students'], 3)
        no_school = get_user_model().objects.create_user(username='student-unassigned', role='trustee')
        self.client.force_authenticate(no_school)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_invalid_filters_and_to_date_without_from(self):
        for filters in [{'from_date': 'bad'}, {'from_date': '2025-06-01', 'to_date': '2025-05-01'}, {'student_status': 'bad'}, {'page_size': 101}, {'page': 0}]:
            self.assertEqual(self.client.get(self.url, filters).status_code, 400)
        self.report(to_date='2025-05-01')

    def test_inactive_is_not_implicitly_dropout_or_transfer(self):
        StudentFieldValue.objects.filter(student=self.b, field__label__iexact='Student status').delete()
        summary = self.report()['summary']
        self.assertEqual(summary['inactive'], 1)
        self.assertEqual((summary['dropouts'], summary['transferred']), (0, 0))

    def test_explicit_transfer_and_category_from_dynamic_fields(self):
        self.field(self.a, 'Leaving reason', 'Transferred')
        self.field(self.a, 'Category', 'OBC')
        report = self.report(student_status='transferred')
        self.assertEqual(report['students']['count'], 1)
        self.assertEqual(report['students']['results'][0]['category'], 'OBC')

    def test_unconfigured_year_dates_are_disclosed(self):
        self.year.start_month = None
        self.year.end_month = None
        self.year.save()
        report = self.report(academic_year=self.year.pk)
        self.assertTrue(any('no configured month boundaries' in note for note in report['notes']))
        self.assertEqual(report['summary']['new_admissions'], 1)
