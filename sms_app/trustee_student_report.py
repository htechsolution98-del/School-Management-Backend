"""Read-only student oversight; no recalculation/save methods are called."""
import calendar
import re
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (School, Staff, Student, AcademicYear, SchoolClass, Division,
                     StudentExtraData, StudentFieldValue, StudentAttendance,
                     StudentFee, StudentFeePayment, Result, FinalStudentResult)
from .trustee_inventory_report import IsTrustee, money
from .utils import format_report_timestamp


def percent(numerator, denominator):
    return round(float(numerator / denominator * 100), 2) if denominator else None


def key(value):
    return re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower()).strip('_')


class StudentReportFilters(serializers.Serializer):
    academic_year = serializers.IntegerField(required=False, min_value=1)
    school_class = serializers.IntegerField(required=False, min_value=1)
    division = serializers.CharField(required=False, max_length=20)
    student_status = serializers.ChoiceField(required=False, choices=['active', 'inactive', 'transferred', 'dropout', 'left_unspecified'])
    search = serializers.CharField(required=False, max_length=200, allow_blank=True)
    student = serializers.IntegerField(required=False, min_value=1)
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    page = serializers.IntegerField(default=1, min_value=1)
    page_size = serializers.IntegerField(default=25, min_value=1, max_value=100)
    export_all = serializers.BooleanField(default=False)

    def validate(self, attrs):
        today = timezone.localdate()
        if attrs.get('from_date') and attrs.get('to_date') and attrs['from_date'] > attrs['to_date']:
            raise serializers.ValidationError('From date must be on or before To date.')
        if attrs.get('from_date', today) > today or attrs.get('to_date', today) > today:
            raise serializers.ValidationError('Report dates cannot be in the future.')
        return attrs


class TrusteeStudentReport(APIView):
    permission_classes = [IsAuthenticated, IsTrustee]

    def get(self, request):
        filters = StudentReportFilters(data=request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data
        school = getattr(request.user, 'school', None)
        if not school:
            member = Staff.objects.filter(user=request.user).select_related('school').first()
            school = member.school if member else None
        if not school:
            school = School.objects.filter(login_id=request.user).first()
        if not school:
            raise PermissionDenied('No school is assigned to your account.')
        years = list(AcademicYear.objects.filter(school=school).order_by('name', 'id'))
        classes = list(SchoolClass.objects.filter(school=school).order_by('school_class', 'id'))
        year_map = {year.pk: year for year in years}
        if params.get('academic_year') and params['academic_year'] not in year_map:
            raise serializers.ValidationError({'academic_year': 'Select an academic year from your school.'})
        if params.get('school_class') and params['school_class'] not in {c.pk for c in classes}:
            raise serializers.ValidationError({'school_class': 'Select a class from your school.'})
        year = year_map.get(params.get('academic_year'))
        start, end = params.get('from_date'), params.get('to_date')
        year_start = year_end = None
        if year and year.get_start_year() and year.start_month and year.end_month:
            start_year = year.get_start_year()
            end_year = start_year + (year.end_month < year.start_month)
            year_start = date(start_year, year.start_month, 1)
            year_end = date(end_year, year.end_month, calendar.monthrange(end_year, year.end_month)[1])
        start = max(d for d in [start, year_start] if d) if start or year_start else None
        end = min(d for d in [end, year_end, timezone.localdate()] if d)

        students = Student.objects.filter(school=school).select_related('school_class', 'academic_year', 'admission__form')
        if params.get('student'):
            if not students.filter(pk=params['student']).exists():
                raise NotFound('Student not found for your school.')
            students = students.filter(pk=params['student'])
        if params.get('school_class'):
            students = students.filter(school_class_id=params['school_class'])
        if params.get('division'):
            students = students.filter(division__iexact=params['division'])
        if params.get('search'):
            for token in params['search'].split():
                students = students.filter(Q(name__icontains=token) | Q(surname__icontains=token) | Q(gr_no__icontains=token) | Q(roll_no__icontains=token) | Q(mobile__icontains=token))
        students = list(students.order_by('school_class__school_class', 'division', 'name', 'surname', 'id'))
        ids = [student.pk for student in students]
        extras = {}
        for extra in StudentExtraData.objects.filter(student_id__in=ids).order_by('updated_at', 'id'):
            extras[extra.student_id] = extra
        dynamic = defaultdict(dict)
        aliases = {
            'gender': 'gender', 'sex': 'gender', 'student_gender': 'gender',
            'category': 'category', 'caste_category': 'category', 'social_category': 'category', 'scheduled_caste': 'category',
            'student_status': 'exit', 'enrollment_status': 'exit', 'leaving_reason': 'exit', 'exit_reason': 'exit', 'transfer_status': 'exit',
        }
        values = StudentFieldValue.objects.filter(student_id__in=ids).filter(Q(school=school) | Q(school__isnull=True)).filter(
            Q(field__school=school) | Q(field__school__isnull=True, field__section__form__school=school)
        ).select_related('field').order_by('created_at', 'id')
        for value in values:
            field_key = key(value.field.map_to_student_field) or key(value.field.label)
            field_type = aliases.get(field_key)
            if field_type and value.value and str(value.value).strip():
                dynamic[value.student_id][field_type] = str(value.value).strip()
        profiles = {}
        for student in students:
            extra = extras.get(student.pk)
            raw_gender = key(dynamic[student.pk].get('gender'))
            gender = 'Male' if raw_gender in ['male', 'm', 'boy'] else 'Female' if raw_gender in ['female', 'f', 'girl'] else 'Other' if raw_gender in ['other', 'non_binary', 'nonbinary', 'transgender'] else 'Not recorded'
            social = dynamic[student.pk].get('category') or (extra.scheduled_caste if extra else None) or 'Not recorded'
            exit_value = key(dynamic[student.pk].get('exit'))
            status = 'transferred' if exit_value in ['transferred', 'transfer', 'transfer_out', 'transferred_out'] else 'dropout' if exit_value in ['dropout', 'dropped_out', 'drop_out'] else 'left_unspecified' if extra and extra.leaving_date else 'active' if student.is_active else 'inactive'
            profiles[student.pk] = {'gender': gender, 'category': social, 'student_status': status, 'leaving_date': extra.leaving_date if extra else None}
        if params.get('student_status'):
            # Active/inactive uses the authoritative flag; exit filters use explicit exit data.
            status = params['student_status']
            students = [student for student in students if (student.is_active == (status == 'active') if status in ['active', 'inactive'] else profiles[student.pk]['student_status'] == status)]
        ids = [student.pk for student in students]
        # Historical participation is only known from current placement, admission
        # year and stored final-result rows. Do not fabricate promotion history.
        memberships = defaultdict(set)
        for student in students:
            if student.academic_year_id in year_map:
                memberships[student.academic_year_id].add(student.pk)
            if student.admission and student.admission.school_id == school.pk and student.admission.form and student.admission.form.school_id == school.pk:
                admission_year = student.admission.form.academic_year_id
                if admission_year in year_map:
                    memberships[admission_year].add(student.pk)
        historical = FinalStudentResult.objects.filter(school=school, student_id__in=ids, academic_year__school=school).values_list('academic_year_id', 'student_id')
        for year_id, student_id in historical:
            memberships[year_id].add(student_id)
        trends = [{'id': y.pk, 'year': y.name, 'recorded_students': len(memberships[y.pk])} for y in years]
        if year:
            students = [student for student in students if student.pk in memberships[year.pk]]
        ids = [student.pk for student in students]
        student_map = {student.pk: student for student in students}

        attendance = StudentAttendance.objects.filter(school=school, student_id__in=ids, attendance_date__lte=end)
        if start:
            attendance = attendance.filter(attendance_date__gte=start)
        attendance_stats = defaultdict(Counter)
        attendance_daily = defaultdict(Counter)
        for row in attendance.values('student_id', 'attendance_date', 'is_present', 'is_absent'):
            state = 'present' if row['is_present'] and not row['is_absent'] else 'absent' if row['is_absent'] and not row['is_present'] else 'unmarked'
            attendance_stats[row['student_id']][state] += 1
            attendance_daily[str(row['attendance_date'])][state] += 1

        fees = StudentFee.objects.filter(student_id__in=ids, student__school=school).filter(Q(school=school) | Q(school__isnull=True)).exclude(status='cancelled').select_related('student', 'feetype', 'academic_year')
        if year:
            fees = fees.filter(academic_year=year)
        fee_stats = defaultdict(lambda: defaultdict(lambda: Decimal('0')))
        fee_rows = []
        for fee in fees:
            stat = fee_stats[fee.student_id]
            stat['payable'] += fee.payable_amount
            stat['credited_paid'] += fee.paid_amount
            stat['pending'] += fee.balance_amount
            stat['govt_pending'] += fee.rte_govt_balance_amount
            if fee.due_date and fee.due_date < timezone.localdate():
                stat['overdue_due'] += fee.balance_amount
            fee_rows.append({'id': fee.pk, 'student_id': fee.student_id, 'fee_type': fee.feetype.name, 'academic_year': fee.academic_year.name if fee.academic_year else None,
                             'due_date': fee.due_date, 'status': fee.status, 'payable': money(fee.payable_amount), 'credited_paid': money(fee.paid_amount),
                             'pending': money(fee.balance_amount), 'govt_pending': money(fee.rte_govt_balance_amount)})
        payments = StudentFeePayment.objects.filter(student_id__in=ids, student__school=school, student_fee__student_id__in=ids, is_bounced=False).filter(
            Q(school=school) | Q(school__isnull=True)
        ).filter(Q(student_fee__school=school) | Q(student_fee__school__isnull=True)).filter(Q(is_verified=True) | ~Q(payment_mode='cheque')).exclude(student_fee__status='cancelled')
        if year:
            payments = payments.filter(student_fee__academic_year=year)
        payment_months = defaultdict(lambda: {'student_collection': Decimal('0'), 'government_collection': Decimal('0')})
        for payment in payments:
            payment_day = timezone.localdate(payment.payment_date or payment.created_at)
            if payment_day > end or (start and payment_day < start):
                continue
            field = 'government_collection' if payment.payer_type == 'government' else 'student_collection'
            fee_stats[payment.student_id][field] += payment.amount
            payment_months[str(payment_day)[:7]][field] += payment.amount

        results = Result.objects.filter(student_id__in=ids, exam__school=school).filter(Q(is_published=True) | Q(status='VERIFIED')).select_related('exam__subject', 'exam__academic_year', 'exam__exam_term__academic_year')
        if year:
            results = results.filter(Q(exam__academic_year=year) | Q(exam__academic_year__isnull=True, exam__exam_term__academic_year=year))
        results = results.filter(exam__exam_date__lte=end)
        if start:
            results = results.filter(exam__exam_date__gte=start)
        marks = defaultdict(lambda: {'obtained': Decimal('0'), 'maximum': Decimal('0'), 'count': 0})
        exam_groups = {}
        result_rows = []
        for result in results.order_by('-exam__exam_date', 'exam_id', 'student_id'):
            valid = result.max_marks > 0 and (result.is_absent or (result.marks_obtained is not None and 0 <= result.marks_obtained <= result.max_marks))
            obtained = Decimal('0') if result.is_absent else result.marks_obtained
            passing = result.exam.passing_marks / result.exam.max_marks * result.max_marks if result.exam.max_marks > 0 else None
            passed = valid and not result.is_absent and passing is not None and obtained >= passing
            if valid:
                stat = marks[result.student_id]
                stat['obtained'] += obtained
                stat['maximum'] += result.max_marks
                stat['count'] += 1
            exam = result.exam
            if exam.pk not in exam_groups:
                exam_groups[exam.pk] = {'id': exam.pk, 'title': exam.title, 'subject': exam.subject.name if exam.subject else None, 'date': exam.exam_date, 'records': 0, 'graded': 0, 'passed': 0, 'absent': 0, '_obtained': Decimal('0'), '_maximum': Decimal('0')}
            group = exam_groups[exam.pk]
            group['records'] += 1
            group['absent'] += result.is_absent
            if valid:
                group['graded'] += 1
                group['passed'] += passed
                group['_obtained'] += obtained
                group['_maximum'] += result.max_marks
            student = student_map[result.student_id]
            result_rows.append({'id': result.pk, 'student_id': student.pk, 'student_name': f'{student.name or ""} {student.surname or ""}'.strip(), 'gr_no': student.gr_no,
                                'exam': exam.title, 'subject': exam.subject.name if exam.subject else None, 'date': exam.exam_date,
                                'marks_obtained': str(obtained) if obtained is not None else None, 'max_marks': str(result.max_marks),
                                'percentage': percent(obtained, result.max_marks) if valid else None, 'outcome': 'Absent' if result.is_absent else 'Not graded' if not valid else 'Pass' if passed else 'Fail',
                                'grade': result.grade, 'status': result.status, 'published': result.is_published})
        exam_rows = []
        for group in exam_groups.values():
            group['average_percentage'] = percent(group.pop('_obtained'), group.pop('_maximum'))
            group['pass_percentage'] = percent(group['passed'], group['graded'])
            exam_rows.append(group)
        finals = FinalStudentResult.objects.filter(school=school, student_id__in=ids, academic_year__school=school).filter(Q(is_published=True) | Q(status='PUBLISHED'))
        if year:
            finals = finals.filter(academic_year=year)
        final_map = {}
        for final in finals.select_related('academic_year').order_by('academic_year__name', 'updated_at', 'id'):
            final_map[final.student_id] = final

        rows = []
        for student in students:
            profile = profiles[student.pk]
            att = attendance_stats[student.pk]
            fee = fee_stats[student.pk]
            academic = marks[student.pk]
            final = final_map.get(student.pk)
            admission_year = student.admission.form.academic_year_id if student.admission and student.admission.school_id == school.pk and student.admission.form and student.admission.form.school_id == school.pk else None
            new_admission = bool(student.admission_date and student.admission_date <= end and (not start or student.admission_date >= start))
            if year and not start:
                new_admission = admission_year == year.pk
            rows.append({
                'id': student.pk, 'name': f'{student.name or ""} {student.surname or ""}'.strip() or f'Student #{student.pk}', 'gr_no': student.gr_no, 'roll_no': student.roll_no,
                'class_id': student.school_class_id, 'class_name': str(student.school_class) if student.school_class and student.school_class.school_id == school.pk else 'Unassigned',
                'division': student.division or 'Unassigned', 'academic_year': student.academic_year.name if student.academic_year_id in year_map else 'Unassigned',
                'is_active': student.is_active, 'is_rte': student.is_rte, **profile,
                'date_of_birth': student.date_of_birth, 'father_name': student.father_name, 'mother_name': student.mother_name, 'mobile': student.mobile,
                'admission_date': student.admission_date, 'new_admission': new_admission,
                'present': att['present'], 'absent': att['absent'], 'unmarked': att['unmarked'], 'attendance_percentage': percent(att['present'], att['present'] + att['absent']),
                **{field: money(fee[field]) for field in ['payable', 'credited_paid', 'pending', 'govt_pending', 'overdue_due', 'student_collection', 'government_collection']},
                'exam_percentage': percent(academic['obtained'], academic['maximum']), 'graded_results': academic['count'],
                'final_percentage': float(final.total_percentage) if final else None, 'final_grade': final.grade if final else None,
                'final_year': final.academic_year.name if final else None,
            })
        def strength(group_fields):
            groups = {}
            for row in rows:
                group_key = tuple(row[field] for field in group_fields)
                if group_key not in groups:
                    groups[group_key] = {field: row[field] for field in group_fields}
                    groups[group_key].update({'id': '|'.join(str(v) for v in group_key), 'total': 0, 'active': 0, 'inactive': 0, 'new_admissions': 0, '_present': 0, '_absent': 0, '_pending': Decimal('0')})
                group = groups[group_key]
                group['total'] += 1
                group['active'] += row['is_active']
                group['inactive'] += not row['is_active']
                group['new_admissions'] += row['new_admission']
                group['_present'] += row['present']
                group['_absent'] += row['absent']
                group['_pending'] += Decimal(row['pending'])
            for group in groups.values():
                present, absent = group.pop('_present'), group.pop('_absent')
                group['attendance_percentage'] = percent(present, present + absent)
                group['pending'] = money(group.pop('_pending'))
            return list(groups.values())
        total_present = sum(row['present'] for row in rows)
        total_absent = sum(row['absent'] for row in rows)
        available_finals = [row['final_percentage'] for row in rows if row['final_percentage'] is not None]
        summary = {'total_students': len(rows), 'active': sum(row['is_active'] for row in rows), 'inactive': sum(not row['is_active'] for row in rows),
                   'new_admissions': sum(row['new_admission'] for row in rows), 'transferred': sum(row['student_status'] == 'transferred' for row in rows),
                   'dropouts': sum(row['student_status'] == 'dropout' for row in rows), 'left_unspecified': sum(row['student_status'] == 'left_unspecified' for row in rows),
                   'rte_students': sum(row['is_rte'] for row in rows), 'attendance_percentage': percent(total_present, total_present + total_absent),
                   'attendance_records': total_present + total_absent, 'unmarked_attendance': sum(row['unmarked'] for row in rows),
                   'students_without_attendance': sum(row['attendance_percentage'] is None for row in rows),
                   'published_final_average': round(sum(available_finals) / len(available_finals), 2) if available_finals else None,
                   'published_final_students': len(available_finals), 'gender_missing': sum(row['gender'] == 'Not recorded' for row in rows),
                   'category_missing': sum(row['category'] == 'Not recorded' for row in rows)}
        summary.update({field: money(sum((Decimal(row[field]) for row in rows), Decimal('0'))) for field in ['payable', 'credited_paid', 'pending', 'govt_pending', 'overdue_due', 'student_collection', 'government_collection']})
        admissions_trend = Counter(str(row['admission_date'].year) for row in rows if row['admission_date'])
        attendance_rows = [{'date': day, 'present': stat['present'], 'absent': stat['absent'], 'unmarked': stat['unmarked'], 'percentage': percent(stat['present'], stat['present'] + stat['absent'])} for day, stat in sorted(attendance_daily.items())]
        collection_rows = [{'month': month, **{field: money(amount) for field, amount in values.items()}} for month, values in sorted(payment_months.items())]
        offset = (params['page'] - 1) * params['page_size']
        visible = rows if params['export_all'] else rows[offset:offset + params['page_size']]
        notes = [
            'Student placement is current. Academic-year membership uses current placement, linked admission-form year and stored final-result records; missing historical enrollment cannot be reconstructed. Trends show the selected class/division/status/search cohort across all stored years.',
            'Attendance = present / (present + absent) from marked records only; unmarked/conflicting entries are excluded. No records is shown as unavailable, not 0%.',
            'Fee balances use stored ledger values, exclude cancelled charges and respect RTE exemptions. Date filters affect receipts, not current balances. Bounced and unverified cheque receipts are excluded; government receipts/dues are separate.',
            'Exam aggregates use verified or published results; absent entries count as zero. Published final percentages use the latest stored academic year when All years is selected. Draft marks are excluded.',
            'Transfers/dropouts require an explicit dynamic status/reason. A leaving date without a reason is Left (reason unspecified); inactive does not imply dropout. Gender/category come from configured student fields; unknown data is labelled Not recorded.',
        ]
        if year and not year_start:
            notes.append('This academic year has no configured month boundaries. Attendance/receipt dates use your explicit date filters or all recorded history; fee and exam records still filter by academic-year ID. New admissions use linked admission-form year when no From date is available.')
        if start and start > end:
            notes.append('The selected academic year and date range do not overlap; date-based metrics have no records.')
        return Response({
            'school': school.name, 'generated_at': format_report_timestamp(timezone.now()), 'from_date': start, 'to_date': end,
            'summary': summary, 'students': {'count': len(rows), 'page': params['page'], 'page_size': params['page_size'], 'results': visible},
            'class_strength': strength(['class_id', 'class_name']), 'division_strength': strength(['class_id', 'class_name', 'division']),
            'gender': [{'label': label, 'count': count} for label, count in Counter(row['gender'] for row in rows).items()],
            'categories': [{'label': label, 'count': count} for label, count in Counter(row['category'] for row in rows).items()],
            'status': [{'label': label, 'count': count} for label, count in Counter(row['student_status'] for row in rows).items()],
            'enrollment_trends': trends, 'admission_trends': [{'year': year, 'count': count} for year, count in sorted(admissions_trend.items())],
            'attendance': attendance_rows, 'collections': collection_rows, 'exams': exam_rows,
            'result_records': result_rows if params['export_all'] or params.get('student') else result_rows[:100],
            'result_record_count': len(result_rows),
            'fee_records': fee_rows if params['export_all'] or params.get('student') else [],
            'notes': notes,
            'options': {'academic_years': [{'id': y.pk, 'name': y.name} for y in years], 'classes': [{'id': c.pk, 'name': c.school_class} for c in classes],
                        'divisions': list(Division.objects.filter(school=school, SchoolClass__school=school).order_by('SchoolClass_id', 'division').values('SchoolClass_id', 'division'))},
        })
