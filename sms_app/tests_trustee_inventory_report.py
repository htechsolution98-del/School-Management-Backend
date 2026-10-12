from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import School, Staff, AcademicYear, Student
from .inventory_models import Item, ItemCategory, ItemSize, StockTransaction, Supplier, Purchase, StudentItemIssue


class TrusteeInventoryReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.trustee = User.objects.create_user(username='stock-trustee', role='admin(trustee)')
        owner = User.objects.create_user(username='stock-other-owner', role='trustee')
        self.school = School.objects.create(name='Stock school', code='stock-school', login_id=self.trustee)
        self.other_school = School.objects.create(name='Other stock school', code='stock-other', login_id=owner)
        self.trustee.school = self.school
        self.trustee.save()
        self.category = ItemCategory.objects.create(school=self.school, name='Uniform')
        self.item = Item.objects.create(school=self.school, item_code='SHIRT', item_name='Shirt', category=self.category, minimum_stock_level=12)
        self.empty = Item.objects.create(school=self.school, item_code='EMPTY', item_name='Never received', minimum_stock_level=2)
        self.year = AcademicYear.objects.create(school=self.school, name='2025-26')
        self.txn('OPENING', 10, '2025-01-01', '10')
        self.txn('PURCHASE', 10, '2025-02-01', '20')
        self.txn('ISSUE', -4, '2025-02-02', '0')
        self.txn('RETURN', 2, '2025-02-03', '0')
        self.txn('DAMAGE', -1, '2025-02-04', '0')
        self.txn('ISSUE', -7, '2025-03-01', '0')
        other = Item.objects.create(school=self.other_school, item_code='SECRET', item_name='Other school secret')
        StockTransaction.objects.create(school=self.other_school, item=other, transaction_type='PURCHASE', quantity=999, transaction_date=date(2025, 1, 1))
        self.client = APIClient()
        self.client.force_authenticate(self.trustee)
        self.url = reverse('trustee-inventory-report')

    def txn(self, kind, qty, day, cost='0', **kwargs):
        return StockTransaction.objects.create(school=self.school, item=self.item, transaction_type=kind, quantity=qty, transaction_date=day, unit_purchase_cost=cost, **kwargs)

    def report(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_period_opening_closing_and_current_are_distinct(self):
        data = self.report(from_date='2025-02-01', to_date='2025-02-28')
        row = next(row for row in data['stocks'] if row['item_id'] == self.item.pk)
        self.assertEqual((row['opening_balance'], row['received'], row['issued'], row['returned'], row['other_out']), (10, 10, 4, 2, 1))
        self.assertEqual((row['closing_balance'], row['current_balance']), (17, 10))
        self.assertEqual((row['closing_stock_value'], row['current_stock_value']), ('255.00', '150.00'))
        self.assertEqual(data['daily'][-1]['closing_balance'], 17)
        self.assertEqual(data['daily'][0]['opening_balance'], 10)

    def test_school_scope_ignores_external_school_header(self):
        response = self.client.get(self.url, {'school': self.other_school.pk}, HTTP_X_SCHOOL_ID=str(self.other_school.pk))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('Other school secret', str(response.data))
        self.assertEqual(len(response.data['options']['items']), 2)

    def test_empty_inventory_and_never_stocked_alerts(self):
        data = self.report(item=self.empty.pk)
        self.assertEqual(data['summary']['current_balance'], 0)
        self.assertEqual(data['summary']['out_of_stock_count'], 1)
        self.assertEqual(data['alerts'][0]['item_id'], self.empty.pk)
        data = self.report(item=999999)
        self.assertEqual(data['stocks'], [])
        self.assertEqual(data['transactions']['count'], 0)

    def test_ledger_type_filter_does_not_change_balances(self):
        data = self.report(transaction_type='ISSUE', page_size=1)
        self.assertEqual(data['summary']['current_balance'], 10)
        self.assertEqual(data['transactions']['count'], 2)
        self.assertEqual(len(data['transactions']['results']), 1)
        self.assertEqual(data['transactions']['results'][0]['balance_after'], 10)
        second = self.report(transaction_type='ISSUE', page_size=1, page=2)
        self.assertEqual(second['transactions']['results'][0]['balance_after'], 16)

    def test_invalid_filters_are_400(self):
        for params in [{'from_date': 'bad'}, {'from_date': '2025-03-01', 'to_date': '2025-02-01'}, {'to_date': str(timezone.localdate() + timedelta(days=1))}, {'page': 0}, {'page_size': 101}, {'item': 'wrong'}, {'stock_status': 'wrong'}, {'transaction_type': 'wrong'}]:
            self.assertEqual(self.client.get(self.url, params).status_code, 400, params)

    def test_anonymous_other_roles_and_inactive_are_denied(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])
        for role in ['teacher', 'principal', 'inventory']:
            user = get_user_model().objects.create_user(username=f'stock-{role}', role=role, school=self.school)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.trustee.is_active = False
        self.client.force_authenticate(self.trustee)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_owner_staff_and_group_role_fallback(self):
        self.trustee.school = None
        self.trustee.role = ''
        self.trustee.save()
        group, _ = Group.objects.get_or_create(name='TRUSTEE')
        self.trustee.groups.add(group)
        self.assertEqual(self.report()['school'], self.school.name)
        member_user = get_user_model().objects.create_user(username='stock-staff-trustee')
        Staff.objects.create(school=self.school, user=member_user, name='Board member', category='TRUSTEE')
        self.client.force_authenticate(member_user)
        self.assertEqual(self.report()['school'], self.school.name)

    def test_trustee_without_school_is_denied(self):
        user = get_user_model().objects.create_user(username='stock-no-school', role='trustee')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_variants_negative_and_inactive_alerts(self):
        size = ItemSize.objects.create(school=self.school, name='XL')
        self.txn('ISSUE', -2, '2025-03-02', size=size)
        self.empty.is_active = False
        self.empty.save()
        data = self.report()
        self.assertEqual(data['summary']['negative_stock_count'], 1)
        self.assertEqual(data['summary']['low_stock_count'], 1)
        self.assertEqual(data['summary']['out_of_stock_count'], 0)
        self.assertEqual(len(data['alerts']), 2)
        negative = self.report(stock_status='negative')
        self.assertEqual(negative['stocks'][0]['current_balance'], -2)
        self.assertEqual(negative['summary']['current_stock_value'], '0.00')

    def test_filters_apply_to_stock_and_movements(self):
        data = self.report(category=self.category.pk, search='SHIRT')
        self.assertEqual(len(data['stocks']), 1)
        self.assertEqual(data['transactions']['count'], 6)
        data = self.report(stock_status='out')
        self.assertEqual([row['item_id'] for row in data['stocks']], [self.empty.pk])
        self.assertEqual(data['daily'], [])

    def test_invoice_supplier_and_recipient_details(self):
        supplier = Supplier.objects.create(school=self.school, supplier_name='Uniform vendor')
        purchase = Purchase.objects.create(school=self.school, supplier=supplier, academic_year=self.year, invoice_number='INV-101', purchase_date='2025-04-01')
        self.txn('PURCHASE', 3, '2025-04-01', '12', reference_type='Purchase', reference_id=str(purchase.pk))
        student = Student.objects.create(school=self.school, name='Test', surname='Student')
        issue = StudentItemIssue.objects.create(school=self.school, academic_year=self.year, student=student, item=self.item, quantity=1, charged_amount='25')
        self.txn('ISSUE', -1, '2025-04-02', reference_type='StudentItemIssue', reference_id=str(issue.pk))
        records = self.report(from_date='2025-04-01', to_date='2025-04-30')['transactions']['results']
        student.refresh_from_db()
        supplier.refresh_from_db()
        self.assertEqual(records[0]['recipient'], f'{student.name} {student.surname}')
        self.assertEqual(records[0]['charged_amount'], '25.00')
        self.assertEqual((records[1]['supplier'], records[1]['invoice']), (supplier.supplier_name, 'INV-101'))

    def test_endpoint_is_read_only(self):
        before = StockTransaction.objects.count()
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 405)
        self.assertEqual(self.client.patch(self.url, {}, format='json').status_code, 405)
        self.assertEqual(StockTransaction.objects.count(), before)
