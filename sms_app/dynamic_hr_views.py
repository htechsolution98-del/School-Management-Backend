from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .permissions import IsClerkOrAdmin

from .models import (
    Staff,
    AttendanceSetting,
    AttendanceRegularization,
    LeaveCycle,
    LeaveTemplate,
    LeaveType,
    LeaveBalance,
    SalaryComponent,
    SalaryStructure,
    PayrollRun,
    PayrollPayslip,
)
from .dynamic_hr_serializers import (
    AttendanceSettingSerializer,
    AttendanceRegularizationSerializer,
    LeaveCycleSerializer,
    DynamicLeaveTemplateSerializer,
    DynamicLeaveTypeSerializer,
    LeaveBalanceSerializer,
    DynamicSalaryComponentSerializer,
    SalaryStructureSerializer,
    PayrollRunSerializer,
    PayrollPayslipSerializer,
)


def get_request_school(request):
    """Retrieve school associated with the authenticated user/staff."""
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None
    if hasattr(user, "school") and user.school:
        return user.school
    staff = Staff.objects.filter(user=user).select_related("school").first()
    if staff and staff.school:
        return staff.school
    return None


class AttendanceSettingViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSettingSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return AttendanceSetting.objects.none()
        return AttendanceSetting.objects.filter(school=school).order_by("-is_active", "name")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)


class AttendanceRegularizationViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceRegularizationSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return AttendanceRegularization.objects.none()
        qs = AttendanceRegularization.objects.filter(staff__school=school).select_related(
            "staff", "approved_by"
        )
        staff_id = self.request.query_params.get("staff_id")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        regularization = self.get_object()
        regularization.status = "Approved"
        regularization.approved_by = request.user
        log_entry = {
            "action": "Approved",
            "by": request.user.username,
            "timestamp": timezone.now().isoformat(),
            "note": request.data.get("note", "Approved by administrator"),
        }
        logs = regularization.audit_log or []
        logs.append(log_entry)
        regularization.audit_log = logs
        regularization.save()
        return Response(self.get_serializer(regularization).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        regularization = self.get_object()
        regularization.status = "Rejected"
        regularization.approved_by = request.user
        log_entry = {
            "action": "Rejected",
            "by": request.user.username,
            "timestamp": timezone.now().isoformat(),
            "note": request.data.get("note", "Rejected by administrator"),
        }
        logs = regularization.audit_log or []
        logs.append(log_entry)
        regularization.audit_log = logs
        regularization.save()
        return Response(self.get_serializer(regularization).data)


class LeaveCycleViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveCycleSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return LeaveCycle.objects.none()
        return LeaveCycle.objects.filter(school=school).order_by("-is_active", "-start_date")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)


class LeaveBalanceViewSet(viewsets.ModelViewSet):
    serializer_class = LeaveBalanceSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return LeaveBalance.objects.none()
        qs = LeaveBalance.objects.filter(staff__school=school).select_related(
            "staff", "leave_type", "leave_cycle"
        )
        staff_id = self.request.query_params.get("staff_id")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        cycle_id = self.request.query_params.get("leave_cycle_id")
        if cycle_id:
            qs = qs.filter(leave_cycle_id=cycle_id)
        type_id = self.request.query_params.get("leave_type_id")
        if type_id:
            qs = qs.filter(leave_type_id=type_id)
        return qs


class LeaveTemplateViewSet(viewsets.ModelViewSet):
    serializer_class = DynamicLeaveTemplateSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return LeaveTemplate.objects.none()
        return LeaveTemplate.objects.filter(school=school).order_by("-is_active", "name")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)

    def perform_update(self, serializer):
        school = get_request_school(self.request)
        serializer.save(school=school)

    @action(detail=False, methods=["post"], url_path="bulk_create")
    def bulk_create(self, request):
        school = get_request_school(request)
        from sms_app.library_leave_serializers import LeaveTemplateBulkCreateSerializer, NewLeaveTemplateSerializer
        serializer = LeaveTemplateBulkCreateSerializer(
            data=request.data,
            context={"request": request, "school": school},
        )
        serializer.is_valid(raise_exception=True)
        template = serializer.save()
        return Response(
            NewLeaveTemplateSerializer(template).data,
            status=status.HTTP_201_CREATED,
        )


class LeaveTypeViewSet(viewsets.ModelViewSet):
    serializer_class = DynamicLeaveTypeSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return LeaveType.objects.none()
        qs = LeaveType.objects.filter(leave_template__school=school).select_related(
            "leave_template", "category"
        )
        template_id = self.request.query_params.get("template") or self.request.query_params.get("leave_template")
        if template_id:
            qs = qs.filter(leave_template_id=template_id)
        return qs

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        template = serializer.validated_data.get("leave_template")
        if template and template.school != school:
            raise ValidationError("That leave template does not belong to your school.")
        serializer.save()


class DynamicSalaryComponentViewSet(viewsets.ModelViewSet):
    serializer_class = DynamicSalaryComponentSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return SalaryComponent.objects.none()
        return SalaryComponent.objects.filter(school=school).order_by("name")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)


class SalaryStructureViewSet(viewsets.ModelViewSet):
    serializer_class = SalaryStructureSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return SalaryStructure.objects.none()
        return SalaryStructure.objects.filter(school=school).prefetch_related("components").order_by("name")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)


from sms_app.services.payroll_service import generate_payroll_run, generate_payslip, MissingPunchError


class PayrollRunViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollRunSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return PayrollRun.objects.none()
        return PayrollRun.objects.filter(school=school).order_by("-salary_month")

    def perform_create(self, serializer):
        school = get_request_school(self.request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")
        serializer.save(school=school)

    def perform_update(self, serializer):
        instance = serializer.instance
        new_status = serializer.validated_data.get("status")
        if instance.status == "Locked" and new_status != "Locked" and not self.request.user.is_superuser:
            raise ValidationError("This payroll run is Locked. Only administrators can unlock it.")
        elif instance.status == "Locked" and new_status == "Locked":
            raise ValidationError("This payroll run is Locked and cannot be modified.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status == "Locked":
            raise ValidationError("Cannot delete a Locked payroll run.")
        instance.delete()

    @action(detail=False, methods=["post"], url_path="generate")
    def generate_payroll(self, request):
        school = get_request_school(request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")

        salary_month_str = request.data.get("salary_month")
        if not salary_month_str:
            today = timezone.localdate()
            year, month = today.year, today.month
        else:
            parts = salary_month_str.split("-")
            year, month = int(parts[0]), int(parts[1])

        staff_id = request.data.get("staff_id")
        result = generate_payroll_run(school=school, month=month, year=year, staff_id=staff_id)
        return Response(result)

    @action(detail=True, methods=["post"], url_path="lock")
    def lock_run(self, request, pk=None):
        payroll_run = self.get_object()
        payroll_run.status = "Locked"
        payroll_run.save(update_fields=["status", "updated_at"])
        return Response({
            "status": "success",
            "message": f"Payroll run for {payroll_run.salary_month} is now Locked.",
            "payroll_run": PayrollRunSerializer(payroll_run).data,
        })

    @action(detail=True, methods=["post"], url_path="unlock")
    def unlock_run(self, request, pk=None):
        payroll_run = self.get_object()
        payroll_run.status = "Generated"
        payroll_run.save(update_fields=["status", "updated_at"])
        return Response({
            "status": "success",
            "message": f"Payroll run for {payroll_run.salary_month} is now Unlocked.",
            "payroll_run": PayrollRunSerializer(payroll_run).data,
        })


class PayrollPayslipViewSet(viewsets.ModelViewSet):
    serializer_class = PayrollPayslipSerializer
    permission_classes = [IsAuthenticated, IsClerkOrAdmin]

    def get_queryset(self):
        school = get_request_school(self.request)
        if not school:
            return PayrollPayslip.objects.none()
        qs = PayrollPayslip.objects.filter(payroll_run__school=school).select_related(
            "staff", "payroll_run"
        )
        payroll_run_id = self.request.query_params.get("payroll_run_id")
        if payroll_run_id:
            qs = qs.filter(payroll_run_id=payroll_run_id)
        staff_id = self.request.query_params.get("staff_id")
        if staff_id:
            qs = qs.filter(staff_id=staff_id)
        return qs

    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.payroll_run.status == "Locked":
            raise ValidationError("This payslip belongs to a Locked payroll run and cannot be modified.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.payroll_run.status == "Locked":
            raise ValidationError("Cannot delete a payslip belonging to a Locked payroll run.")
        instance.delete()

    @action(detail=False, methods=["post"], url_path="generate-single")
    def generate_single_payslip(self, request):
        school = get_request_school(request)
        if not school:
            raise ValidationError("Authenticated user is not linked to any school.")

        staff_id = request.data.get("staff_id") or request.data.get("staff")
        if not staff_id:
            raise ValidationError("staff_id is required.")

        salary_month_str = request.data.get("salary_month")
        if not salary_month_str:
            today = timezone.localdate()
            year, month = today.year, today.month
        else:
            parts = salary_month_str.split("-")
            year, month = int(parts[0]), int(parts[1])

        staff = Staff.objects.filter(school=school, id=staff_id).first()
        if not staff:
            raise ValidationError("Staff member not found for this school.")

        try:
            result = generate_payslip(staff=staff, month=month, year=year, raise_on_missing_punch=True)
            return Response(result)
        except MissingPunchError as e:
            return Response(
                {
                    "status": "error",
                    "code": "MISSING_PUNCH",
                    "flag": "Requires Regularization",
                    "message": str(e),
                    "missing_punch_dates": [d.strftime("%Y-%m-%d") for d in e.dates],
                    "staff_id": staff.id,
                    "staff_name": staff.name,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
