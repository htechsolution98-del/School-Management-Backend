"""School-scoped, read-only oversight using operational staff/HR ledgers."""
import calendar
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (School, Staff, Department, AcademicYear, Attendance, AssignClass,
                     LeaveRequest, LeavePerDay, LeaveBalance, PayrollPayslip, StaffSalaryPayment)
from .trustee_inventory_report import IsTrustee, money
from .trustee_staff_access import can_view_salary, can_view_contacts


STATUSES = ['PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE', 'HOLIDAY', 'WEEK_OFF', 'MISSING_PUNCH']
UNAVAILABLE = {
    'employment': 'Probation, contract type/expiry, planned retirement and exit reasons are not maintained. Exits cannot be classified as resignation, retirement or termination.',
    'qualifications': 'Staff qualifications, gender, certifications, skills and prior teaching experience are not maintained in the operational staff records.',
    'performance': 'Performance evaluations, appraisals, training and improvement plans are not maintained.',
    'documents': 'Staff document registry, required-document policy, expiry and verification records are not maintained.',
    'recruitment': 'Approved positions, vacancies, candidates and recruitment pipeline are not maintained. Vacancies cannot be calculated from staff counts.',
}


class StaffReportFilters(serializers.Serializer):
    academic_year = serializers.IntegerField(required=False, min_value=1)
    department = serializers.IntegerField(required=False, min_value=1)
    designation = serializers.CharField(required=False, max_length=100)
    category = serializers.CharField(required=False, max_length=100)
    employment_status = serializers.ChoiceField(required=False, choices=['active', 'inactive', 'exited', 'not_exited'])
    staff = serializers.IntegerField(required=False, min_value=1)
    search = serializers.CharField(required=False, max_length=200, allow_blank=True)
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=25, min_value=1, max_value=100)
    ordering = serializers.ChoiceField(default='name', choices=['name', '-name', 'joining_date', '-joining_date', 'department', '-department', 'attendance_percentage', '-attendance_percentage'])
    export_all = serializers.BooleanField(default=False)

    def validate(self, attrs):
        today = timezone.localdate()
        if attrs.get('from_date', today) > today or attrs.get('to_date', today) > today:
            raise serializers.ValidationError('Activity dates cannot be in the future.')
        if attrs.get('from_date') and attrs.get('to_date') and attrs['from_date'] > attrs['to_date']:
            raise serializers.ValidationError('From date must be on or before To date.')
        return attrs


def attendance_percentage(counts):
    denominator = sum(counts[s] for s in ['PRESENT', 'LATE', 'HALF_DAY', 'ABSENT', 'LEAVE'])
    attended = counts['PRESENT'] + counts['LATE'] + counts['HALF_DAY'] * .5
    return round(attended / denominator * 100, 2) if denominator else None


def distribution(rows, field):
    return [{'label': label, 'count': count} for label, count in sorted(Counter(row[field] for row in rows).items())]


class TrusteeStaffReport(APIView):
    permission_classes = [IsAuthenticated, IsTrustee]

    def get(self, request):
        validator = StaffReportFilters(data=request.query_params)
        validator.is_valid(raise_exception=True)
        p = validator.validated_data
        school = getattr(request.user, 'school', None)
        if not school:
            member = Staff.objects.filter(user=request.user).select_related('school').first()
            school = member.school if member else None
        school = school or School.objects.filter(login_id=request.user).first()
        if not school:
            raise PermissionDenied('No school is assigned to your account.')
        today = timezone.localdate()
        years = list(AcademicYear.objects.filter(school=school).order_by('name'))
        year = next((y for y in years if y.pk == p.get('academic_year')), None)
        if p.get('academic_year') and not year:
            raise serializers.ValidationError({'academic_year': 'Select a year from your school.'})
        departments = list(Department.objects.filter(school=school).order_by('name'))
        if p.get('department') and p['department'] not in [d.pk for d in departments]:
            raise serializers.ValidationError({'department': 'Select a department from your school.'})
        year_start = year_end = None
        if year:
            if not year.get_start_year() or not year.start_month or not year.end_month or not 1 <= year.start_month <= 12 or not 1 <= year.end_month <= 12:
                raise serializers.ValidationError({'academic_year': 'Configure valid start/end months before using this academic-year filter.'})
            y = year.get_start_year()
            last = y + (year.end_month < year.start_month)
            year_start, year_end = date(y, year.start_month, 1), date(last, year.end_month, calendar.monthrange(last, year.end_month)[1])
        start = max(d for d in [p.get('from_date'), year_start] if d) if p.get('from_date') or year_start else date(today.year, 1, 1)
        end = min(d for d in [p.get('to_date'), year_end, today] if d)
        # To-only filters use the start of that calendar year rather than an inverted range.
        if not p.get('from_date') and not year and p.get('to_date'):
            start = date(end.year, 1, 1)
        if start > end:
            raise serializers.ValidationError('Academic year and activity dates do not overlap.')
        salary_allowed, contacts_allowed = can_view_salary(request.user), can_view_contacts(request.user)
        base = Staff.objects.filter(school=school).select_related('department', 'user')
        all_staff = list(base.order_by('name', 'id'))
        if p.get('staff') and not base.filter(pk=p['staff']).exists():
            raise NotFound('Staff member not found for your school.')
        cohort = base
        if p.get('department'):
            cohort = cohort.filter(department_id=p['department'])
        for field in ['designation', 'category']:
            if p.get(field):
                cohort = cohort.filter(**{f'{field}__iexact': p[field]})
        status = p.get('employment_status')
        if status in ['active', 'inactive']:
            cohort = cohort.filter(is_active=status == 'active')
        if status == 'exited':
            cohort = cohort.filter(exit_date__lte=today)
        if status == 'not_exited':
            cohort = cohort.filter(Q(exit_date__isnull=True) | Q(exit_date__gt=today))
        if p.get('staff'):
            cohort = cohort.filter(pk=p['staff'])
        if p.get('search'):
            for token in p['search'].split():
                query = Q(name__icontains=token) | Q(designation__icontains=token) | Q(category__icontains=token)
                if token.isdigit():
                    query |= Q(pk=int(token))
                cohort = cohort.filter(query)
        members = list(cohort.order_by('name', 'id'))
        ids = [m.pk for m in members]
        member_map = {m.pk: m for m in members}
        def department(m):
            return m.department.name if m.department and m.department.school_id == school.pk else 'Unassigned'
        def identity(staff_id):
            m = member_map[staff_id]
            return {'staff_id': m.pk, 'staff_name': m.name or f'Staff #{m.pk}', 'department': department(m)}

        stats = defaultdict(Counter)
        buckets = {unit: defaultdict(Counter) for unit in ['daily', 'weekly', 'monthly', 'yearly']}
        attendance_rows = []
        attendance = Attendance.objects.filter(staff_id__in=ids, staff__school=school, attendance_date__range=(start, end)).filter(Q(school=school) | Q(school__isnull=True))
        for a in attendance.order_by('-attendance_date', 'staff_id'):
            canonical = a.canonical_status
            stats[a.staff_id][canonical] += 1
            stats[a.staff_id]['late_flags'] += a.is_late
            stats[a.staff_id]['early_departure'] += a.is_early_exit
            day = a.attendance_date
            labels = {'daily': str(day), 'weekly': str(day - timedelta(days=day.weekday())), 'monthly': day.strftime('%Y-%m'), 'yearly': str(day.year)}
            for unit, period in labels.items():
                buckets[unit][period][canonical] += 1
            attendance_rows.append({'id': a.pk, **identity(a.staff_id), 'date': day, 'status': canonical, 'late': a.is_late, 'early_departure': a.is_early_exit,
                                    'missing_punch': a.is_missing_punch, 'check_in': a.check_in, 'check_out': a.check_out, 'working_hours': money(Decimal(a.working_hours or 0))})
        attendance_trends = {unit: [{'period': label, **{s.lower(): c[s] for s in STATUSES}, 'percentage': attendance_percentage(c)} for label, c in sorted(periods.items())] for unit, periods in buckets.items()}

        leaves = list(LeaveRequest.objects.filter(staff_id__in=ids, staff__school=school, start_date__lte=end, end_date__gte=start).filter(Q(school=school) | Q(school__isnull=True)).select_related('leave_type__leave_template', 'dynamic_leave_type__leave_template').order_by('-start_date', '-id'))
        leave_ids = [l.pk for l in leaves]
        day_counts = defaultdict(Counter)
        leave_months = defaultdict(lambda: Decimal('0'))
        for day in LeavePerDay.objects.filter(leave_id__in=leave_ids, date__range=(start, end)).filter(Q(school=school) | Q(school__isnull=True)):
            day_counts[day.leave_id][str(day.status or 'UNKNOWN').upper()] += day.day_weight
            if str(day.status).upper() == 'APPROVED':
                leave_months[day.date.strftime('%Y-%m')] += day.day_weight
        leave_stats = defaultdict(Counter)
        leave_rows = []
        for leave in leaves:
            state = str(leave.status or 'UNKNOWN').upper()
            leave_stats[leave.staff_id][state] += 1
            leave_stats[leave.staff_id]['applications'] += 1
            leave_stats[leave.staff_id]['approved_days'] += day_counts[leave.pk]['APPROVED']
            lt = leave.dynamic_leave_type or leave.leave_type
            type_name = lt.leave_type if lt and (not lt.leave_template or lt.leave_template.school_id == school.pk) else 'Unassigned'
            leave_rows.append({'id': leave.pk, **identity(leave.staff_id), 'type': type_name or 'Unassigned', 'start': leave.start_date, 'end': leave.end_date, 'status': state,
                               'application_days': str(leave.total_days or 0), 'approved_days_in_period': str(day_counts[leave.pk]['APPROVED']), 'paid_leave': leave.is_paid, 'cancellation_status': leave.cancellation_status})
        balance_rows = []
        balances = LeaveBalance.objects.filter(staff_id__in=ids, staff__school=school, leave_cycle__school=school, leave_cycle__start_date__lte=end, leave_cycle__end_date__gte=start).filter(
            Q(leave_type__leave_template__school=school) | Q(leave_type__leave_template__isnull=True)
        ).select_related('leave_type', 'leave_cycle')
        for balance in balances:
            balance_rows.append({'id': balance.pk, **identity(balance.staff_id), 'type': balance.leave_type.leave_type, 'cycle': balance.leave_cycle.name,
                                 'cycle_start': balance.leave_cycle.start_date, 'cycle_end': balance.leave_cycle.end_date, 'opening': money(balance.opening_balance),
                                 'allocated': money(balance.allocated), 'carry_forward': money(balance.carry_forward), 'used': money(balance.used), 'pending': money(balance.pending), 'remaining': money(balance.remaining)})

        # Payment and payslip rows are two representations of the same staff/month.
        # Prefer the payment ledger; use the payslip only where no payment exists.
        payroll_rows, component_rows = [], []
        salary_stats = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
        if salary_allowed:
            payments = StaffSalaryPayment.objects.filter(school=school, staff_id__in=ids, staff__school=school, salary_month__gte=start.strftime('%Y-%m'), salary_month__lte=end.strftime('%Y-%m'))
            seen = set()
            for payment in payments.order_by('-salary_month', 'staff_id'):
                if not self.valid_month(payment.salary_month):
                    continue
                seen.add((payment.staff_id, payment.salary_month))
                if payment.payment_status == 'cancelled':
                    continue
                paid = payment.paid_amount if payment.payment_status == 'paid' else Decimal('0')
                pending = max(Decimal('0'), payment.net_salary - paid)
                payroll_rows.append({'id': f'payment-{payment.pk}', **identity(payment.staff_id), 'month': payment.salary_month, 'source': 'Payment ledger', 'status': payment.payment_status,
                                     'gross': money(payment.total_earnings), 'deductions': money(payment.total_deductions), 'net': money(payment.net_salary), 'paid': money(paid), 'pending': money(pending), 'payment_date': payment.payment_date})
                for component in payment.component_snapshot if isinstance(payment.component_snapshot, list) else []:
                    if isinstance(component, dict):
                        component_rows.append({**identity(payment.staff_id), 'month': payment.salary_month, 'component': component.get('name', 'Unnamed'), 'type': component.get('component_type', 'Unspecified'), 'amount': str(component.get('amount', '0'))})
            slips = PayrollPayslip.objects.filter(staff_id__in=ids, staff__school=school, payroll_run__school=school).exclude(payroll_run__status='Draft').select_related('payroll_run')
            for slip in slips:
                month = slip.payroll_run.salary_month.strftime('%Y-%m')
                if (slip.staff_id, month) in seen or not start.strftime('%Y-%m') <= month <= end.strftime('%Y-%m'):
                    continue
                payroll_rows.append({'id': f'payslip-{slip.pk}', **identity(slip.staff_id), 'month': month, 'source': 'Payslip (no payment ledger)', 'status': slip.payroll_run.status,
                                     'gross': money(slip.gross_earnings), 'deductions': money(slip.total_deductions), 'net': money(slip.net_salary), 'paid': '0.00', 'pending': money(slip.net_salary), 'payment_date': None})
                breakdown = slip.component_breakdown if isinstance(slip.component_breakdown, dict) else {}
                for kind in ['earnings', 'deductions']:
                    for component in breakdown.get(kind, []) if isinstance(breakdown.get(kind, []), list) else []:
                        if isinstance(component, dict):
                            component_rows.append({**identity(slip.staff_id), 'month': month, 'component': component.get('name', 'Unnamed'), 'type': kind, 'amount': str(component.get('amount', '0'))})
            for row in payroll_rows:
                for field in ['gross', 'deductions', 'net', 'paid', 'pending']:
                    salary_stats[row['staff_id']][field] += Decimal(row[field])

        assignments = AssignClass.objects.filter(school=school, teacher_id__in=ids, subject__school=school).select_related('subject')
        subjects = defaultdict(set)
        for assignment in assignments:
            subjects[assignment.subject.name].add(assignment.teacher_id)
        staff_subjects = defaultdict(set)
        for subject, teacher_ids in subjects.items():
            for teacher_id in teacher_ids:
                staff_subjects[teacher_id].add(subject)
        rows = []
        for m in members:
            a, l = stats[m.pk], leave_stats[m.pk]
            service_end = min(today, m.exit_date) if m.exit_date else today
            service_days = max(0, (service_end - m.joining_date).days) if m.joining_date else None
            fields = {'name': bool(m.name), 'department': department(m) != 'Unassigned', 'designation': bool(m.designation), 'category': bool(m.category and m.category.upper() != 'OTHER'), 'joining_date': bool(m.joining_date)}
            row = {'id': m.pk, 'name': m.name or f'Staff #{m.pk}', 'department': department(m), 'designation': m.designation or 'Not recorded', 'category': m.category or 'Not recorded',
                   'teaching_group': 'Teaching' if str(m.category).strip().upper() == 'TEACHER' else 'Unclassified' if not m.category or str(m.category).upper() == 'OTHER' else 'Non-teaching',
                   'active': m.is_active, 'status': 'Exited' if m.exit_date and m.exit_date <= today else 'Active' if m.is_active else 'Inactive', 'joining_date': m.joining_date, 'exit_date': m.exit_date,
                   'service_days': service_days, 'service_years': round(service_days / 365.25, 2) if service_days is not None else None, 'subjects': ', '.join(sorted(staff_subjects[m.pk])) or 'Not recorded',
                   **{s.lower(): a[s] for s in STATUSES}, 'late_flags': a['late_flags'], 'early_departure': a['early_departure'], 'attendance_percentage': attendance_percentage(a),
                   'leave_applications': l['applications'], 'approved_leaves': l['APPROVED'], 'pending_leaves': l['PENDING'], 'rejected_leaves': l['REJECTED'], 'approved_leave_days': str(l['approved_days']),
                   'profile_completion': round(sum(fields.values()) / len(fields) * 100), 'missing_profile_fields': ', '.join(f for f, present in fields.items() if not present) or 'None',
                   'qualification_status': 'Not maintained', 'document_status': 'Not maintained', 'created_at': m.created_at}
            if contacts_allowed:
                row.update({'email': m.email, 'mobile': m.mobile})
            if salary_allowed:
                row.update({'base_salary': money(m.salary) if m.salary is not None else None, **{f'payroll_{f}': money(salary_stats[m.pk][f]) for f in ['gross', 'deductions', 'net', 'paid', 'pending']}})
            rows.append(row)

        total_att = Counter()
        for a in stats.values():
            total_att.update(a)
        joined = sum(bool(m.joining_date and start <= m.joining_date <= end) for m in members)
        exits = sum(bool(m.exit_date and start <= m.exit_date <= end) for m in members)
        opening = sum(bool(m.joining_date and m.joining_date <= start and (not m.exit_date or m.exit_date > start)) for m in members)
        closing = sum(bool(m.joining_date and m.joining_date <= end and (not m.exit_date or m.exit_date > end)) for m in members)
        summary = {'total_staff': len(rows), 'active_staff': sum(m.is_active for m in members), 'inactive_staff': sum(not m.is_active for m in members), 'newly_joined': joined, 'recorded_exits': exits,
                   'resigned': None, 'retired': None, 'probation': None, 'contract_based': None, 'attendance_percentage': attendance_percentage(total_att),
                   'missing_punch': total_att['MISSING_PUNCH'], 'late_arrivals': total_att['late_flags'], 'early_departures': total_att['early_departure'],
                   'leave_applications': len(leave_rows), **{f'{state.lower()}_leaves': sum(row['status'] == state for row in leave_rows) for state in ['APPROVED', 'PENDING', 'REJECTED', 'CANCELLED']},
                   'turnover_percentage': round(exits / ((opening + closing) / 2) * 100, 2) if opening + closing and all(m.joining_date for m in members) else None,
                   'profile_completion_average': round(sum(r['profile_completion'] for r in rows) / len(rows), 2) if rows else None,
                   'without_attendance': sum(r['attendance_percentage'] is None for r in rows)}
        payroll_months, payroll_years, payroll_departments = [], [], []
        if salary_allowed:
            summary.update({f'payroll_{f}': money(sum((Decimal(r[f]) for r in payroll_rows), Decimal('0'))) for f in ['gross', 'deductions', 'net', 'paid', 'pending']})
            payroll_months = self.payroll_groups(payroll_rows, 'month')
            payroll_years = self.payroll_groups([{**r, 'year': r['month'][:4]} for r in payroll_rows], 'year')
            payroll_departments = self.payroll_groups(payroll_rows, 'department')
        # Strength uses recorded joining/exit dates; current active flags cannot recreate history.
        strength_trends = []
        cursor = date(start.year, start.month, 1)
        while cursor <= end:
            last = min(end, date(cursor.year, cursor.month, calendar.monthrange(cursor.year, cursor.month)[1]))
            known = sum(bool(m.joining_date and m.joining_date <= last and (not m.exit_date or m.exit_date > last)) for m in members)
            month_joined = sum(bool(m.joining_date and cursor <= m.joining_date <= last) for m in members)
            month_exited = sum(bool(m.exit_date and cursor <= m.exit_date <= last) for m in members)
            month_open = sum(bool(m.joining_date and m.joining_date <= cursor and (not m.exit_date or m.exit_date > cursor)) for m in members)
            strength_trends.append({'month': cursor.strftime('%Y-%m'), 'recorded_strength': known, 'joined': month_joined, 'exited': month_exited,
                                    'turnover_percentage': round(month_exited / ((month_open + known) / 2) * 100, 2) if month_open + known and all(m.joining_date for m in members) else None})
            cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        field = p['ordering'].lstrip('-')
        rows.sort(key=lambda r: (r[field] is not None, r[field] if r[field] is not None else '', r['id']), reverse=p['ordering'].startswith('-'))
        count = len(rows)
        offset = (p['page'] - 1) * p['page_size']
        full = p['export_all'] or bool(p.get('staff'))
        notes = [
            'Activity defaults to the current calendar year. Academic year uses configured date boundaries; staff directory and status are current, not historical placements.',
            'Attendance uses each stored record\'s canonical_status. Percentage = (present + late + 0.5 × half-day) / (present + late + half-day + absent + leave). Holidays, week-offs and missing punches are excluded. Unrecorded days are not inferred as absence; no denominator is unavailable.',
            'Late/early flags may overlap canonical attendance categories. Weekly periods start Monday. Missing punch follows the existing check-in-without-check-out rule.',
            'Leave applications overlap the selected dates; application days describe the full application. Approved days/utilization use recorded LeavePerDay weights within the period. Missing day rows are not reconstructed. Balances are current snapshots for cycles overlapping the period, not historical balances.',
            'Payroll uses salary-month overlap, including whole months for partial date ranges. Payment ledger takes precedence over synchronized payslips, avoiding double counting. Cancelled payments and draft-only payslips are excluded. Unpaid/pending ledger rows contribute zero paid; payslips without payments are pending. Paid values reflect stored ledger status, not bank reconciliation.',
            'Allowances/deductions use saved component snapshots; overtime is identifiable only when named in a stored component. No salary calculations or payroll processing run during reporting.',
            'Strength/turnover use recorded joining/exit dates for the filtered current staff cohort. Turnover = exits / average opening and closing recorded headcount; unavailable when joining dates are missing. Deleted staff and multiple employment episodes cannot be reconstructed. Resigned/retired/terminated cannot be inferred from an exit date.',
            'Service duration uses joining date through today or exit date. It is tenure, not prior teaching experience. Profile completion measures name, department, designation, category and joining date only; it does not certify document compliance.',
            'Subject distribution counts distinct assigned staff per subject; one teacher can appear in multiple subjects. Teaching uses the explicit TEACHER category; OTHER/blank is unclassified. Gender and qualification cannot be inferred.',
        ]
        return Response({'school': school.name, 'generated_at': timezone.now(), 'from_date': start, 'to_date': end,
            'permissions': {'salary': salary_allowed, 'contacts': contacts_allowed}, 'unavailable': UNAVAILABLE, 'summary': summary,
            'staff': {'count': count, 'page': p['page'], 'page_size': p['page_size'], 'results': rows if p['export_all'] else rows[offset:offset + p['page_size']]},
            'distribution': {'department': distribution(rows, 'department'), 'designation': distribution(rows, 'designation'), 'category': distribution(rows, 'category'), 'teaching': distribution(rows, 'teaching_group'), 'subjects': [{'label': name, 'count': len(teacher_ids)} for name, teacher_ids in sorted(subjects.items())]},
            'attendance': attendance_trends, 'attendance_records': attendance_rows if full else attendance_rows[:200], 'attendance_record_count': len(attendance_rows),
            'leave_records': leave_rows if full else leave_rows[:200], 'leave_record_count': len(leave_rows), 'leave_types': self.leave_groups(leave_rows, 'type'), 'leave_departments': self.leave_groups(leave_rows, 'department'),
            'leave_balances': balance_rows if full else balance_rows[:200], 'leave_balance_count': len(balance_rows), 'leave_trends': [{'month': month, 'approved_days': str(days)} for month, days in sorted(leave_months.items())],
            'payroll_records': payroll_rows if full else payroll_rows[:200], 'payroll_record_count': len(payroll_rows), 'payroll_components': component_rows if full else component_rows[:200], 'payroll_component_count': len(component_rows),
            'payroll_months': payroll_months, 'payroll_years': payroll_years, 'payroll_departments': payroll_departments, 'strength_trends': strength_trends,
            'frequent_absence': sorted([{'staff_id': r['id'], 'staff_name': r['name'], 'absent': r['absent'], 'leave': r['leave'], 'missing_punch': r['missing_punch']} for r in rows if r['absent'] or r['leave']], key=lambda r: (-r['absent'], -r['leave'], r['staff_id'])),
            'notes': notes, 'options': {'academic_years': [{'id': y.pk, 'name': y.name} for y in years], 'departments': [{'id': d.pk, 'name': d.name} for d in departments],
                'designations': sorted({m.designation for m in all_staff if m.designation}), 'categories': sorted({m.category for m in all_staff if m.category}), 'staff': [{'id': m.pk, 'name': m.name or f'Staff #{m.pk}'} for m in all_staff]}})

    @staticmethod
    def valid_month(value):
        try:
            return len(value) == 7 and date.fromisoformat(value + '-01').strftime('%Y-%m') == value
        except (ValueError, TypeError):
            return False

    @staticmethod
    def payroll_groups(rows, field):
        groups = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
        for row in rows:
            for amount in ['gross', 'deductions', 'net', 'paid', 'pending']:
                groups[row[field]][amount] += Decimal(row[amount])
        return [{field: name, **{f: money(v) for f, v in amounts.items()}} for name, amounts in sorted(groups.items())]

    @staticmethod
    def leave_groups(rows, field):
        groups = defaultdict(lambda: {'applications': 0, 'approved': 0, 'pending': 0, 'rejected': 0, 'cancelled': 0, 'approved_days': Decimal('0')})
        for row in rows:
            group = groups[row[field]]
            group['applications'] += 1
            state = row['status'].lower()
            if state in ['approved', 'pending', 'rejected', 'cancelled']:
                group[state] += 1
            group['approved_days'] += Decimal(row['approved_days_in_period'])
        return [{field: name, **{f: str(v) if isinstance(v, Decimal) else v for f, v in values.items()}} for name, values in sorted(groups.items())]
