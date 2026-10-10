from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .permissions import IsClerkOrAdmin, IsHRAttendanceAdmin

from .models import (
    Staff,
    Attendance,
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


def get_staff_for_user(user):
    """Retrieve staff record linked to user via FK, email, or mobile."""
    if not user or not getattr(user, "is_authenticated", False):
        return None
    staff = Staff.objects.filter(user=user).select_related("school").first()
    if not staff:
        try:
            staff = getattr(user, "staff", None)
        except Exception:
            staff = None
    if not staff and getattr(user, "email", None):
        staff = Staff.objects.filter(email=user.email).select_related("school").first()
    if not staff and getattr(user, "mobile", None):
        staff = Staff.objects.filter(mobile=user.mobile).select_related("school").first()
    return staff


def is_user_hr_management(user):
    """
    Check if the user has school-wide HR/Attendance management authority.
    Explicitly returns False for Librarian, Inventory, Fees Management, and regular staff.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    role = str(getattr(user, "role", "") or "").strip().upper()
    if role in ["FEES MANAGEMENT", "FEE MANAGEMENT", "LIBRARIAN", "INVENTORY", "STUDENT", "PARENT"]:
        return False
    from .permissions import CLERK_ROLES, CLERK_GROUPS
    if role in CLERK_ROLES or role in [
        "HR", "HR_ADMIN", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN"
    ]:
        return True
    staff = get_staff_for_user(user)
    if staff:
        cat = str(getattr(staff, "category", "") or "").strip().upper()
        if cat in ["FEES MANAGEMENT", "FEE MANAGEMENT", "LIBRARIAN", "INVENTORY"]:
            return False
        if cat in CLERK_ROLES or cat in ["HR", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN"]:
            return True
    return (
        user.groups.filter(name__in=[
            "PRINCIPAL", "principal", "Principal",
            "VICE PRINCIPAL", "vice principal", "Vice Principal",
            "admin(trustee)", "trustee", "Trustee",
            "ADMIN", "admin", "Admin",
            "super_admin", "superadmin", "Super Admin",
            "HR", "hr",
        ] + CLERK_GROUPS).exclude(name__in=["FEES MANAGEMENT", "Fee Management", "fees management"]).exists()
    )


class AttendanceSettingViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSettingSerializer
    permission_classes = [IsAuthenticated, IsHRAttendanceAdmin]

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

    def get_permissions(self):
        if self.action in ["approve", "reject"]:
            return [IsAuthenticated(), IsHRAttendanceAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        school = get_request_school(self.request)
        if not school:
            return AttendanceRegularization.objects.none()

        qs = AttendanceRegularization.objects.filter(staff__school=school).select_related(
            "staff", "approved_by"
        )

        is_mgmt = is_user_hr_management(user)

        if not is_mgmt:
            # Regular staff (Teacher, Librarian, Inventory, Fees Management, etc.):
            # ONLY view their own regularization requests.
            current_staff = get_staff_for_user(user)
            if not current_staff:
                return AttendanceRegularization.objects.none()
            qs = qs.filter(staff=current_staff)
        else:
            # Management roles can filter by specific staff_id
            staff_id = self.request.query_params.get("staff_id")
            if staff_id:
                qs = qs.filter(staff_id=staff_id)

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        is_mgmt = is_user_hr_management(user)
        school = get_request_school(self.request)

        user_staff = get_staff_for_user(user)

        if not is_mgmt:
            # Regular employees MUST ALWAYS use authenticated user's staff profile.
            # Client-supplied staff ID is strictly ignored and untrusted.
            if not user_staff:
                raise ValidationError({"staff": "No staff profile linked to authenticated user."})
            staff = user_staff
        else:
            # Management creating a request: can specify staff from their school or default to own
            client_staff = serializer.validated_data.get("staff")
            if client_staff:
                if school and client_staff.school_id != school.id:
                    raise ValidationError({"staff": "Specified staff does not belong to your school."})
                staff = client_staff
            else:
                if not user_staff:
                    raise ValidationError({"staff": "No staff profile linked to authenticated user."})
                staff = user_staff

        initial_log = [
            {
                "action": "Requested",
                "by": user.id if user and getattr(user, "is_authenticated", False) else None,
                "by_username": getattr(user, "username", ""),
                "timestamp": timezone.now().isoformat(),
                "reason": serializer.validated_data.get("reason", ""),
            }
        ]
        serializer.save(staff=staff, audit_log=initial_log)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()
        is_mgmt = is_user_hr_management(user)

        if not is_mgmt:
            current_staff = get_staff_for_user(user)
            if not current_staff or instance.staff_id != current_staff.id:
                raise PermissionDenied("You can only update your own regularization request.")
            if instance.status != "Pending":
                raise ValidationError("Only pending regularization requests can be updated.")
            serializer.validated_data.pop("staff", None)
        else:
            client_staff = serializer.validated_data.get("staff")
            if client_staff and client_staff.school_id != instance.staff.school_id:
                raise ValidationError({"staff": "Specified staff does not belong to the school."})

        logs = list(instance.audit_log or [])
        logs.append({
            "action": "Updated",
            "by": user.id,
            "by_username": getattr(user, "username", ""),
            "timestamp": timezone.now().isoformat(),
            "reason": serializer.validated_data.get("reason", instance.reason),
        })
        serializer.save(audit_log=logs)

    def perform_destroy(self, instance):
        user = self.request.user
        is_mgmt = is_user_hr_management(user)

        if not is_mgmt:
            current_staff = get_staff_for_user(user)
            if not current_staff or instance.staff_id != current_staff.id:
                raise PermissionDenied("You can only delete your own regularization request.")
            if instance.status != "Pending":
                raise ValidationError("Only pending regularization requests can be deleted.")
        else:
            if instance.status not in ["Pending", "Rejected"]:
                raise ValidationError("Approved regularization requests cannot be deleted directly.")

        instance.delete()

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        regularization = self.get_object()

        # Strict rule: Staff cannot approve their own regularization request
        current_staff = get_staff_for_user(request.user)
        if (
            regularization.staff.user_id == request.user.id
            or (current_staff and regularization.staff_id == current_staff.id)
        ):
            return Response(
                {"error": "You cannot approve your own regularization request."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 1. Update or create underlying Attendance record
        attendance, _ = Attendance.objects.get_or_create(
            staff=regularization.staff,
            attendance_date=regularization.attendance_date,
            defaults={
                "school": regularization.staff.school,
                "name": regularization.staff.name,
                "category": regularization.staff.category,
                "is_present": True,
            },
        )

        orig_in = attendance.check_in.isoformat() if attendance.check_in else None
        orig_out = attendance.check_out.isoformat() if attendance.check_out else None

        att_date = regularization.attendance_date
        new_in_dt = None
        new_out_dt = None

        if regularization.requested_check_in:
            naive_in = datetime.combine(att_date, regularization.requested_check_in)
            new_in_dt = timezone.make_aware(naive_in) if timezone.is_naive(naive_in) else naive_in
            attendance.check_in = new_in_dt

        if regularization.requested_check_out:
            naive_out = datetime.combine(att_date, regularization.requested_check_out)
            new_out_dt = timezone.make_aware(naive_out) if timezone.is_naive(naive_out) else naive_out
            attendance.check_out = new_out_dt

        attendance.is_present = True
        attendance.source = "Regularization"

        # Working hours
        if attendance.check_in and attendance.check_out:
            duration = attendance.check_out - attendance.check_in
            total_sec = max(0.0, duration.total_seconds())
            attendance.working_hours = round(Decimal(str(total_sec)) / Decimal("3600.0"), 2)

        # Policy recalculation:
        policy = getattr(regularization.staff, "attendance_setting", None)
        if not policy and regularization.staff.school:
            policy = AttendanceSetting.objects.filter(school=regularization.staff.school, is_active=True).first()

        if policy and policy.check_in_time and regularization.requested_check_in:
            c_sec = (
                regularization.requested_check_in.hour * 3600
                + regularization.requested_check_in.minute * 60
                + regularization.requested_check_in.second
            )
            t_sec = (
                policy.check_in_time.hour * 3600
                + policy.check_in_time.minute * 60
                + policy.check_in_time.second
            )
            diff_mins = (c_sec - t_sec) / 60.0
            attendance.is_late = diff_mins > policy.grace_period_mins
            attendance.is_half_day = diff_mins > policy.half_day_threshold_mins
        else:
            attendance.is_late = False
            attendance.is_half_day = False

        if policy and policy.check_out_time and regularization.requested_check_out:
            c_sec = (
                regularization.requested_check_out.hour * 3600
                + regularization.requested_check_out.minute * 60
                + regularization.requested_check_out.second
            )
            t_sec = (
                policy.check_out_time.hour * 3600
                + policy.check_out_time.minute * 60
                + policy.check_out_time.second
            )
            early_diff_mins = (t_sec - c_sec) / 60.0
            attendance.is_early_exit = early_diff_mins > (policy.grace_period_mins or 0)
            if early_diff_mins > policy.half_day_threshold_mins:
                attendance.is_half_day = True
        else:
            attendance.is_early_exit = False

        attendance.save()

        # 2. Append to audit log and update regularization
        current_time = timezone.now().isoformat()
        log_entry = {
            "action": "Approved",
            "by": request.user.id,
            "by_username": request.user.username,
            "timestamp": current_time,
            "original_punch": {
                "check_in": orig_in,
                "check_out": orig_out,
            },
            "new_punch": {
                "check_in": new_in_dt.isoformat() if new_in_dt else None,
                "check_out": new_out_dt.isoformat() if new_out_dt else None,
                "requested_check_in": str(regularization.requested_check_in) if regularization.requested_check_in else None,
                "requested_check_out": str(regularization.requested_check_out) if regularization.requested_check_out else None,
            },
            "note": request.data.get("note", "Regularization approved"),
        }
        logs = list(regularization.audit_log or [])
        logs.append(log_entry)
        regularization.audit_log = logs
        regularization.status = "Approved"
        regularization.approved_by = request.user
        regularization.save(update_fields=["status", "approved_by", "audit_log", "updated_at"])

        return Response(self.get_serializer(regularization).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        regularization = self.get_object()

        # Strict rule: Staff cannot reject their own regularization request
        current_staff = get_staff_for_user(request.user)
        if (
            regularization.staff.user_id == request.user.id
            or (current_staff and regularization.staff_id == current_staff.id)
        ):
            return Response(
                {"error": "You cannot reject your own regularization request."},
                status=status.HTTP_403_FORBIDDEN,
            )

        current_time = timezone.now().isoformat()
        log_entry = {
            "action": "Rejected",
            "by": request.user.id,
            "by_username": request.user.username,
            "timestamp": current_time,
            "note": request.data.get("note", "Regularization rejected"),
        }
        logs = list(regularization.audit_log or [])
        logs.append(log_entry)
        regularization.audit_log = logs
        regularization.status = "Rejected"
        regularization.approved_by = request.user
        regularization.save(update_fields=["status", "approved_by", "audit_log", "updated_at"])

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
