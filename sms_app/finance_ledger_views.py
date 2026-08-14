from decimal import Decimal
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import Student, StudentFee, FeeWiseClass, FeeType, AcademicYear
from .finance_serializers import StudentFeeSerializer
from django.utils import timezone

class StudentLedgerScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student_id = request.query_params.get("student")
        academic_year_id = request.query_params.get("academic_year")

        if not student_id:
            return Response({"error": "student query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(id=student_id).first()
        if not student:
            return Response({"error": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        academic_year = None
        if academic_year_id:
            academic_year = AcademicYear.objects.filter(id=academic_year_id).first()

        if not academic_year:
            academic_year = (
                AcademicYear.objects.filter(school=student.school, is_active=True).first()
                or AcademicYear.objects.filter(school=student.school).first()
                or AcademicYear.objects.first()
            )

        if not academic_year:
            now_year = timezone.now().year
            academic_year, _ = AcademicYear.objects.get_or_create(
                name=f"{now_year}-{now_year + 1}",
                defaults={
                    "school": student.school,
                    "is_active": True,
                    "start_month": 4,
                    "end_month": 3,
                }
            )

        try:
            start_year = int(academic_year.name.split("-")[0])
        except Exception:
            start_year = timezone.now().year

        start_month = academic_year.start_month or 4
        end_month = academic_year.end_month or 3

        months_list = []
        current_year = start_year
        current_month = start_month
        for _ in range(12):
            months_list.append((current_year, current_month))
            if current_month == end_month:
                break
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

        fee_structures = FeeWiseClass.objects.filter(
            school=student.school,
            school_class=student.school_class,
        ).select_related("feetype")
        actual_fees = StudentFee.objects.filter(
            student=student, 
            academic_year=academic_year
        ).select_related("feetype", "fee_wise_class").prefetch_related("payments")
        
        for fee in actual_fees:
            fee.apply_late_fee()
            
        actual_fees_by_key = {}
        for fee in actual_fees:
            key = f"{fee.feetype_id}_{fee.billing_period}"
            actual_fees_by_key[key] = fee

        
        today = timezone.localdate()
        
        def calculate_virtual_penalty(structure, due_date_str):
            if not structure.late_fee_enabled: return Decimal('0.00')
            try:
                due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                penalty_start = due_date + timedelta(days=structure.grace_days)
                if today > penalty_start:
                    if structure.late_fee_type == "fixed":
                        late_fee = structure.late_fee_amount
                    elif structure.late_fee_type == "per_day":
                        late_fee = structure.late_fee_amount * (today - penalty_start).days
                    else:
                        late_fee = Decimal('0.00')
                    if structure.max_late_fee is not None:
                        late_fee = min(late_fee, structure.max_late_fee)
                    return late_fee
            except Exception:
                pass
            return Decimal('0.00')

        def make_virtual_fee(structure, billing_period, due_date_str):
            penalty = calculate_virtual_penalty(structure, due_date_str)
            payable = structure.amount + penalty

            return {
                "id": f"virtual_{structure.feetype_id}_{billing_period}",
                "is_virtual": True,
                "feetype": structure.feetype_id,
                "feetype_name": structure.feetype.name,
                "fee_wise_class": structure.id,
                "billing_period": billing_period,
                "amount": str(structure.amount),
                "discount_amount": "0.00",
                "late_fee_amount": str(structure.late_fee_amount) if structure.late_fee_amount else "0.00",
                "fine_amount": str(penalty),
                "paid_amount": "0.00",
                "balance_amount": str(payable),
                "payable_amount": str(payable),
                "status": "pending",
                "late_fee_enabled": structure.late_fee_enabled,
                "grace_days": structure.grace_days,
                "late_fee_type": structure.late_fee_type,
                "due_date": due_date_str,
            }

        def append_fee_or_virtual(structure, billing_period, due_date_str):
            key = f"{structure.feetype_id}_{billing_period}"
            if key in actual_fees_by_key:
                actual_fee = actual_fees_by_key[key]
                actual_fee.refresh_payment_status()
                data = StudentFeeSerializer(actual_fee, context={"request": request}).data
                data["is_virtual"] = False
                projected_ledger.append(data)
            else:
                projected_ledger.append(
                    make_virtual_fee(structure, billing_period, due_date_str)
                )

        def grouped_periods(group_size, prefix):
            periods = []
            for index in range(0, len(months_list), group_size):
                group = months_list[index:index + group_size]
                if not group:
                    continue
                period_number = (index // group_size) + 1
                first_year, first_month = group[0]
                billing_period = f"{academic_year.name}-{prefix}{period_number}"
                due_date_str = f"{first_year}-{first_month:02d}-15"
                periods.append((billing_period, due_date_str))
            return periods

        projected_ledger = []
        
        for structure in fee_structures:
            if structure.feetype.billing_cycle == 'monthly':
                for year, month in months_list:
                    billing_period = f"{year}-{month:02d}"
                    due_date_str = f"{year}-{month:02d}-10"
                    append_fee_or_virtual(structure, billing_period, due_date_str)
                        
            elif structure.feetype.billing_cycle == 'quarterly':
                for billing_period, due_date_str in grouped_periods(3, "Q"):
                    append_fee_or_virtual(structure, billing_period, due_date_str)

            elif structure.feetype.billing_cycle == 'half_yearly':
                for billing_period, due_date_str in grouped_periods(6, "H"):
                    append_fee_or_virtual(structure, billing_period, due_date_str)

            elif structure.feetype.billing_cycle in ['yearly', 'single']:
                billing_period = academic_year.name
                due_date_str = f"{start_year}-{start_month:02d}-15"
                append_fee_or_virtual(structure, billing_period, due_date_str)

        return Response(projected_ledger)


class GenerateSingleStudentFeeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student_id = request.data.get("student")
        academic_year_id = request.data.get("academic_year")
        fee_wise_class_id = request.data.get("fee_wise_class")
        billing_period = request.data.get("billing_period")

        if not all([student_id, academic_year_id, fee_wise_class_id, billing_period]):
            return Response({"error": "Missing required fields"}, status=status.HTTP_400_BAD_REQUEST)

        student = Student.objects.filter(id=student_id).first()
        academic_year = AcademicYear.objects.filter(id=academic_year_id).first()
        fee_wise_class = FeeWiseClass.objects.filter(id=fee_wise_class_id).first()

        if not student or not academic_year or not fee_wise_class:
            return Response({"error": "Invalid IDs provided"}, status=status.HTTP_404_NOT_FOUND)

        existing = StudentFee.objects.filter(
            student=student, 
            academic_year=academic_year, 
            fee_wise_class=fee_wise_class, 
            billing_period=billing_period
        ).first()

        if existing:
            existing.apply_late_fee(save=True)
            return Response(StudentFeeSerializer(existing, context={"request": request}).data)

        due_date = request.data.get("due_date")
        if not due_date:
            try:
                if "-" in billing_period and len(billing_period) == 7:
                    due_date = f"{billing_period}-10"
                else:
                    due_date = timezone.now().date()
            except Exception:
                due_date = timezone.now().date()

        fee = StudentFee.objects.create(
            school=request.user.school,
            academic_year=academic_year,
            student=student,
            feetype=fee_wise_class.feetype,
            fee_wise_class=fee_wise_class,
            billing_period=billing_period,
            amount=fee_wise_class.amount,
            late_fee_enabled=fee_wise_class.late_fee_enabled,
            grace_days=fee_wise_class.grace_days,
            late_fee_type=fee_wise_class.late_fee_type,
            late_fee_amount=fee_wise_class.late_fee_amount,
            max_late_fee=fee_wise_class.max_late_fee,
            due_date=due_date,
            status="pending"
        )
        fee.apply_late_fee(save=True)
        
        return Response(StudentFeeSerializer(fee, context={"request": request}).data, status=status.HTTP_201_CREATED)
