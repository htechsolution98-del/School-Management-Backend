from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (School, Staff, Department, AcademicYear, Attendance, LeaveTemplate, LeaveType,
                     LeaveRequest, LeavePerDay, LeaveCycle, LeaveBalance, PayrollRun, PayrollPayslip,
                     StaffSalaryPayment, Module, UserModuleAccess, SchoolClass, Division, Subject, AssignClass)


class TrusteeStaffReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='staff-report-owner', role='admin(trustee)')
        self.school = School.objects.create(name='Staff report school', code='staff-reports', login_id=self.user)
        owner = User.objects.create_user(username='staff-report-other', role='trustee')
        self.other_school = School.objects.create(name='Other staff school', code='other-staff-reports', login_id=owner)
        self.user.school = self.school
        self.user.save()
        self.department = Department.objects.create(school=self.school, name='Academic')
        self.a = Staff.objects.create(school=self.school, name='Alice Teacher', department=self.department, designation='Senior Teacher', category='TEACHER', joining_date='2024-04-01', salary=Decimal('1000'), email='private@example.com', mobile='9998887776')
        self.b = Staff.objects.create(school=self.school, name='Bob Clerk', category='CLERK', is_active=False, joining_date='2025-04-01', exit_date='2025-08-01')
        self.c = Staff.objects.create(school=self.school, name='Carol Unknown', category='OTHER')
        self.other = Staff.objects.create(school=self.other_school, name='Secret staff', salary=99999)
        self.year = AcademicYear.objects.create(school=self.school, name='2025-26', start_month=4, end_month=3)
        self.att(self.a, '2025-05-01', is_present=True)
        self.att(self.a, '2025-05-02', is_present=True, is_late=True, is_early_exit=True)
        self.att(self.a, '2025-05-03', is_present=True, is_half_day=True)
        self.att(self.a, '2025-05-04', source='Leave')
        self.att(self.a, '2025-05-05')
        self.att(self.a, '2025-05-06', source='Holiday')
        self.att(self.a, '2025-05-07', source='Week Off')
        self.att(self.a, '2025-05-08', is_present=True, check_in=timezone.make_aware(datetime(2025, 5, 8, 9)))
        self.template = LeaveTemplate.objects.create(school=self.school, name='Annual')
        self.type = LeaveType.objects.create(leave_template=self.template, leave_type='Casual')
        self.leave = LeaveRequest.objects.create(school=self.school, staff=self.a, leave_type=self.type, start_date='2025-05-03', end_date='2025-05-04', total_days=Decimal('1.5'), status='APPROVED', reason='Private health reason')
        LeavePerDay.objects.create(school=self.school, leave=self.leave, date='2025-05-03', status='APPROVED', day_weight=Decimal('.5'))
        LeavePerDay.objects.create(school=self.school, leave=self.leave, date='2025-05-04', status='APPROVED', day_weight=1)
        LeaveRequest.objects.create(school=self.school, staff=self.b, leave_type=self.type, start_date='2025-05-02', end_date='2025-05-02', status='PENDING')
        cycle = LeaveCycle.objects.create(school=self.school, name='2025', start_date='2025-01-01', end_date='2025-12-31')
        LeaveBalance.objects.create(staff=self.a, leave_type=self.type, leave_cycle=cycle, opening_balance=2, allocated=10, carry_forward=1, used=Decimal('1.5'), pending=1)
        self.run = PayrollRun.objects.create(school=self.school, salary_month='2025-05-01', status='Generated')
        self.slip = PayrollPayslip.objects.create(staff=self.a, payroll_run=self.run, gross_earnings=1200, total_deductions=200, net_salary=1000)
        self.payment = self.pay(self.a, '2025-05', 'paid', 1000, 1000)
        self.pay(self.b, '2025-05', 'pending', 500, 500)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.url = reverse('trustee-staff-report')

    def att(self, staff, day, **kwargs):
        return Attendance.objects.create(school=staff.school, staff=staff, attendance_date=day, **kwargs)

    def pay(self, staff, month, status, net, paid):
        return StaffSalaryPayment.objects.create(school=staff.school, staff=staff, salary_month=month, payment_status=status, payment_mode='offline',
            total_earnings=net + 200, total_deductions=200, net_salary=net, paid_amount=paid,
            component_snapshot=[{'name': 'Overtime', 'component_type': 'earning', 'amount': '100'}])

    def grant_salary(self):
        permission = Permission.objects.get(content_type__app_label='sms_app', codename='view_staffsalarypayment')
        self.user.user_permissions.add(permission)
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)

    def report(self, **params):
        response = self.client.get(self.url, {'from_date': '2025-04-01', 'to_date': '2025-08-31', **params})
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_overview_and_unavailable_are_honest(self):
        r = self.report()
        s = r['summary']
        self.assertEqual((s['total_staff'], s['active_staff'], s['inactive_staff'], s['newly_joined'], s['recorded_exits']), (3, 2, 1, 1, 1))
        for field in ['resigned', 'retired', 'probation', 'contract_based', 'turnover_percentage']:
            self.assertIsNone(s[field])
        self.assertIn('performance', r['unavailable'])

    def test_canonical_attendance_percentage_and_all_periods(self):
        r = self.report()
        self.assertEqual(r['summary']['attendance_percentage'], 50)
        self.assertEqual((r['summary']['missing_punch'], r['summary']['late_arrivals'], r['summary']['early_departures']), (1, 1, 1))
        for unit in ['daily', 'weekly', 'monthly', 'yearly']:
            self.assertTrue(r['attendance'][unit])
        may = r['attendance']['monthly'][0]
        for field in ['present', 'absent', 'late', 'half_day', 'leave', 'holiday', 'week_off', 'missing_punch']:
            self.assertEqual(may[field], 1)
        self.assertIsNone(next(row for row in r['staff']['results'] if row['id'] == self.c.pk)['attendance_percentage'])

    def test_leave_days_and_balance_business_rule(self):
        r = self.report()
        self.assertEqual((r['summary']['leave_applications'], r['summary']['approved_leaves'], r['summary']['pending_leaves']), (2, 1, 1))
        self.assertEqual(r['leave_types'][0]['approved_days'], '1.50')
        self.assertEqual(r['leave_balances'][0]['remaining'], '10.50')
        self.assertNotIn('reason', r['leave_records'][0])
        clipped = self.report(from_date='2025-05-04', to_date='2025-05-04')
        self.assertEqual(Decimal(clipped['leave_types'][0]['approved_days']), 1)

    def test_salary_and_contacts_are_omitted_without_grants(self):
        r = self.report(export_all='true')
        self.assertEqual(r['permissions'], {'salary': False, 'contacts': False})
        self.assertNotIn('payroll_net', r['summary'])
        self.assertEqual(r['payroll_records'], [])
        for row in r['staff']['results']:
            for key in ['email', 'mobile', 'base_salary', 'payroll_net', 'address', 'date_of_birth']:
                self.assertNotIn(key, row)

    def test_payroll_dedup_and_pending_not_counted_paid(self):
        self.grant_salary()
        r = self.report(export_all='true')
        self.assertEqual(len(r['payroll_records']), 2)
        self.assertEqual((r['summary']['payroll_net'], r['summary']['payroll_paid'], r['summary']['payroll_pending']), ('1500.00', '1000.00', '500.00'))
        self.assertEqual(r['payroll_years'][0]['net'], '1500.00')
        self.assertEqual(len(r['payroll_components']), 2)

    def test_cancelled_payment_suppresses_synchronized_payslip(self):
        self.grant_salary()
        StaffSalaryPayment.objects.filter(pk=self.payment.pk).update(payment_status='cancelled')
        self.assertEqual(self.report()['summary']['payroll_net'], '500.00')

    def test_payslip_fallback_and_draft_exclusion(self):
        self.grant_salary()
        self.payment.delete()
        r = self.report()
        self.assertEqual((r['summary']['payroll_net'], r['summary']['payroll_pending']), ('1500.00', '1500.00'))
        PayrollRun.objects.filter(pk=self.run.pk).update(status='Draft')
        self.assertEqual(self.report()['summary']['payroll_net'], '500.00')

    def test_active_assigned_salary_module_and_contact_permission(self):
        module = Module.objects.create(name='Payroll', code='PAYROLL')
        UserModuleAccess.objects.create(user=self.user, module=module)
        self.user.user_permissions.add(Permission.objects.get(content_type__app_label='sms_app', codename='view_staff'))
        self.user = get_user_model().objects.get(pk=self.user.pk)
        self.client.force_authenticate(self.user)
        r = self.report(staff=self.a.pk)
        self.assertTrue(r['permissions']['salary'])
        self.assertEqual(r['staff']['results'][0]['email'], 'private@example.com')
        module.is_active = False
        module.save()
        self.assertFalse(self.report()['permissions']['salary'])

    def test_school_scope_and_cross_school_ids(self):
        r = self.report(export_all='true')
        self.assertNotIn(self.other.pk, [row['id'] for row in r['staff']['results']])
        other_year = AcademicYear.objects.create(school=self.other_school, name='2025-26')
        other_department = Department.objects.create(school=self.other_school, name='Secret department')
        for params in [{'academic_year': other_year.pk}, {'department': other_department.pk}]:
            self.assertEqual(self.client.get(self.url, params).status_code, 400)
        self.assertEqual(self.client.get(self.url, {'staff': self.other.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.url, HTTP_X_SCHOOL_ID=str(self.other_school.pk)).data['summary']['total_staff'], 3)

    def test_attendance_and_leave_foreign_school_rows_excluded(self):
        Attendance.objects.create(school=self.other_school, staff=self.a, attendance_date='2025-05-09', is_present=True)
        LeaveRequest.objects.create(school=self.other_school, staff=self.a, start_date='2025-05-09', end_date='2025-05-09', status='APPROVED')
        r = self.report()
        self.assertEqual(r['attendance_record_count'], 8)
        self.assertEqual(r['leave_record_count'], 2)

    def test_filters_search_pagination_sort_and_export(self):
        self.assertEqual(self.report(department=self.department.pk)['staff']['count'], 1)
        self.assertEqual(self.report(category='CLERK')['staff']['count'], 1)
        self.assertEqual(self.report(employment_status='exited')['staff']['count'], 1)
        self.assertEqual(self.report(search='Alice Teacher')['staff']['results'][0]['id'], self.a.pk)
        self.assertEqual(self.report(designation='Senior Teacher')['staff']['count'], 1)
        first = self.report(page_size=1, ordering='-name')
        self.assertEqual(first['staff']['results'][0]['id'], self.c.pk)
        self.assertEqual(len(self.report(page_size=1, export_all='true')['staff']['results']), 3)
        self.assertEqual(self.report(page_size=1, page=2)['staff']['results'][0]['id'], self.b.pk)

    def test_academic_year_dates_and_invalid_filters(self):
        self.assertEqual(self.report(academic_year=self.year.pk)['from_date'], date(2025, 4, 1))
        for params in [{'from_date': 'bad'}, {'from_date': '2025-09-01', 'to_date': '2025-08-01'}, {'page': 0}, {'page_size': 101}, {'ordering': 'salary'}, {'employment_status': 'retired'}]:
            self.assertEqual(self.client.get(self.url, params).status_code, 400)
        self.assertEqual(self.client.get(self.url, {'to_date': '2025-05-01'}).status_code, 200)
        self.year.start_month = None
        self.year.save()
        self.assertEqual(self.client.get(self.url, {'academic_year': self.year.pk}).status_code, 400)

    def test_subject_distribution_deduplicates_teacher(self):
        school_class = SchoolClass.objects.create(school=self.school, school_class='1')
        division = Division.objects.create(school=self.school, SchoolClass=school_class, division='A')
        subject = Subject.objects.create(school=self.school, division=division, name='Maths')
        for _ in range(2):
            AssignClass.objects.create(school=self.school, teacher=self.a, subject=subject, division=division)
        r = self.report()
        self.assertEqual(r['distribution']['subjects'], [{'label': 'maths', 'count': 1}])
        self.assertEqual({row['label']: row['count'] for row in r['distribution']['teaching']}, {'Teaching': 1, 'Non-teaching': 1, 'Unclassified': 1})

    def test_no_write_services_or_model_saves(self):
        self.grant_salary()
        with patch.object(Staff, 'save', side_effect=AssertionError('No writes')), patch.object(LeaveBalance, 'save', side_effect=AssertionError('No writes')), patch.object(StaffSalaryPayment, 'save', side_effect=AssertionError('No writes')):
            self.report(export_all='true')

    def test_roles_anonymous_and_report_methods(self):
        for role in ['principal', 'teacher', 'clerk', 'student']:
            user = get_user_model().objects.create_user(username=f'staff-report-{role}', role=role, school=self.school)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])
        self.client.force_authenticate(self.user)
        for method in ['post', 'put', 'patch', 'delete']:
            self.assertEqual(getattr(self.client, method)(self.url, {}, format='json').status_code, 405)

    def test_legacy_mutations_are_denied_including_action_overrides(self):
        endpoints = [('/api/StaffView/', 'post'), ('/api/v1/staff-hr/staff/', 'post'), ('/api/StaffView/1/', 'patch'),
            ('/api/departments/', 'post'), ('/api/attendance/', 'post'), ('/api/attendance-settings/', 'post'),
            ('/api/attendance-regularizations/1/approve/', 'post'), ('/api/leave-request/1/approve/', 'post'),
            ('/api/leave-request/1/reject/', 'post'), ('/api/approve-all-leave/1/', 'patch'),
            ('/api/change-leave-status/1/', 'patch'), ('/api/leave-cycles/', 'post'), ('/api/leave-types/', 'post'),
            ('/api/payroll-runs/generate/', 'post'), ('/api/payroll-payslips/generate-single/', 'post'),
            ('/api/staff-salary-payment/', 'post'), ('/api/staff-salary-component/', 'post'), ('/api/salary-component/', 'post'),
            (reverse('staff-activation-set-status', args=[self.a.pk]), 'patch')]
        for url, method in endpoints:
            with self.subTest(url=url):
                self.assertEqual(getattr(self.client, method)(url, {}, format='json').status_code, 403)

    def test_legacy_sensitive_reads_cannot_bypass_permissions(self):
        for url in ['/api/StaffView/', '/api/staff-list/', '/api/staff-salary-payment/', '/api/payroll-payslips/']:
            self.assertEqual(self.client.get(url).status_code, 403)
        self.grant_salary()
        # The legacy route retains its original additional role policy.
        self.assertTrue(self.report()['permissions']['salary'])
        self.assertEqual(self.client.post('/api/staff-salary-payment/', {}, format='json').status_code, 403)

    def test_group_trustee_and_owner_fallback(self):
        self.user.role = ''
        self.user.school = None
        self.user.save()
        group, _ = Group.objects.get_or_create(name='TRUSTEE')
        self.user.groups.add(group)
        self.assertEqual(self.report()['summary']['total_staff'], 3)
        user = get_user_model().objects.create_user(username='unassigned-staff-report', role='trustee')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_governance_summary_cannot_leak_salary_aggregate(self):
        response = self.client.get('/api/trustee/analytics/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['financials']['total_payroll_expenditure'])
        self.grant_salary()
        response = self.client.get('/api/trustee/analytics/')
        self.assertIsNotNone(response.data['financials']['total_payroll_expenditure'])
