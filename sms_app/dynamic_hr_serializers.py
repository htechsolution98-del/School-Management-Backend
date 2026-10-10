from rest_framework import serializers
from .models import (
    Staff,
    Attendance,
    AttendanceSetting,
    AttendanceRegularization,
    LeaveCycle,
    LeaveTemplate,
    LeaveType,
    LeaveBalance,
    LeaveTransaction,
    SalaryComponent,
    SalaryStructure,
    PayrollRun,
    PayrollPayslip,
)


class AttendanceSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceSetting
        fields = [
            "id",
            "school",
            "name",
            "check_in_time",
            "check_out_time",
            "grace_period_mins",
            "half_day_threshold_mins",
            "geo_required",
            "geo_radius_meters",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "created_at", "updated_at"]


class AttendanceRegularizationSerializer(serializers.ModelSerializer):
    staff = serializers.PrimaryKeyRelatedField(
        queryset=Staff.objects.all(), required=False, allow_null=True
    )
    staff_name = serializers.CharField(source="staff.name", read_only=True, default=None)
    approved_by_username = serializers.CharField(source="approved_by.username", read_only=True, default=None)
    original_check_in = serializers.SerializerMethodField()
    original_check_out = serializers.SerializerMethodField()
    attendance_date = serializers.DateField(
        input_formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ", "iso-8601"]
    )
    requested_check_in = serializers.TimeField(
        required=False, allow_null=True, input_formats=["%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "iso-8601"]
    )
    requested_check_out = serializers.TimeField(
        required=False, allow_null=True, input_formats=["%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p", "iso-8601"]
    )

    class Meta:
        model = AttendanceRegularization
        fields = [
            "id",
            "staff",
            "staff_name",
            "attendance_date",
            "requested_check_in",
            "requested_check_out",
            "reason",
            "status",
            "approved_by",
            "approved_by_username",
            "audit_log",
            "original_check_in",
            "original_check_out",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "approved_by", "audit_log", "created_at", "updated_at"]
        extra_kwargs = {
            "staff": {"required": False, "allow_null": True},
        }

    def get_original_check_in(self, obj):
        att = Attendance.objects.filter(staff=obj.staff, attendance_date=obj.attendance_date).first()
        if att and att.check_in:
            return att.check_in.strftime("%H:%M:%S")
        return None

    def get_original_check_out(self, obj):
        att = Attendance.objects.filter(staff=obj.staff, attendance_date=obj.attendance_date).first()
        if att and att.check_out:
            return att.check_out.strftime("%H:%M:%S")
        return None

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        staff = attrs.get("staff") or getattr(self.instance, "staff", None)
        if not staff and user:
            from .models import Staff
            staff = Staff.objects.filter(user=user).first()
            if not staff and getattr(user, "email", None):
                staff = Staff.objects.filter(email=user.email).first()
            if not staff and getattr(user, "mobile", None):
                staff = Staff.objects.filter(mobile=user.mobile).first()

        if staff:
            if not staff.is_active:
                raise serializers.ValidationError(
                    {"staff": "Inactive staff cannot request attendance regularization."}
                )

            att_date = attrs.get("attendance_date") or getattr(self.instance, "attendance_date", None)
            if att_date:
                if staff.joining_date and att_date < staff.joining_date:
                    raise serializers.ValidationError(
                        {"attendance_date": f"Cannot regularize attendance before joining date ({staff.joining_date})."}
                    )
                if staff.exit_date and att_date > staff.exit_date:
                    raise serializers.ValidationError(
                        {"attendance_date": f"Cannot regularize attendance after exit date ({staff.exit_date})."}
                    )

        return attrs


class LeaveCycleSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(source="closed_by.username", read_only=True, default=None)

    class Meta:
        model = LeaveCycle
        fields = [
            "id",
            "school",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "is_closed",
            "closed_at",
            "closed_by",
            "closed_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "closed_at", "closed_by", "created_at", "updated_at"]


class DynamicLeaveTemplateSerializer(serializers.ModelSerializer):
    leave_types = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = LeaveTemplate
        fields = [
            "id",
            "school",
            "name",
            "time_line",
            "description",
            "is_active",
            "created_at",
            "leave_types",
        ]
        read_only_fields = ["id", "school", "created_at"]

    def get_leave_types(self, obj):
        if hasattr(obj, "leave_types"):
            return DynamicLeaveTypeSerializer(obj.leave_types.all(), many=True).data
        if hasattr(obj, "leavetype_set"):
            return DynamicLeaveTypeSerializer(obj.leavetype_set.all(), many=True).data
        return []


class DynamicLeaveTypeSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="leave_template.name", read_only=True, default=None)

    class Meta:
        model = LeaveType
        fields = [
            "id",
            "leave_template",
            "template_name",
            "name",
            "code",
            "leave_type",
            "is_paid",
            "allocation_count",
            "allocation_period",
            "carry_forward",
            "max_carry_forward",
            "allow_encashment",
            "is_active",
            "max_consecutive_days",
            "half_day_allowed",
            "include_weekends",
            "include_holidays",
            "allow_negative_balance",
            "allow_future_leave",
            "allow_backdated_leave",
            "max_backdated_days",
            "prorata_on_joining",
            "category",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class LeaveBalanceSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True, default=None)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True, default=None)
    leave_cycle_name = serializers.CharField(source="leave_cycle.name", read_only=True, default=None)
    remaining = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)
    available = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = LeaveBalance
        fields = [
            "id",
            "staff",
            "staff_name",
            "leave_type",
            "leave_type_name",
            "leave_cycle",
            "leave_cycle_name",
            "opening_balance",
            "allocated",
            "carry_forward",
            "used",
            "pending",
            "remaining",
            "available",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "staff",
            "staff_name",
            "leave_type",
            "leave_type_name",
            "leave_cycle",
            "leave_cycle_name",
            "opening_balance",
            "allocated",
            "carry_forward",
            "used",
            "pending",
            "remaining",
            "available",
            "created_at",
            "updated_at",
        ]


class LeaveTransactionSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True, default=None)
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True, default=None)
    leave_cycle_name = serializers.CharField(source="leave_cycle.name", read_only=True, default=None)
    created_by_name = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = LeaveTransaction
        fields = [
            "id",
            "school",
            "staff",
            "staff_name",
            "leave_type",
            "leave_type_name",
            "leave_cycle",
            "leave_cycle_name",
            "leave_request",
            "transaction_type",
            "amount",
            "balance_after",
            "description",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "school", "balance_after", "created_at"]


class DynamicSalaryComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryComponent
        fields = [
            "id",
            "school",
            "name",
            "type",
            "component_type",
            "calc_type",
            "calc_base",
            "value",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "created_at", "updated_at"]


class SalaryStructureSerializer(serializers.ModelSerializer):
    components_detail = DynamicSalaryComponentSerializer(source="components", many=True, read_only=True)

    class Meta:
        model = SalaryStructure
        fields = [
            "id",
            "school",
            "name",
            "components",
            "components_detail",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "created_at", "updated_at"]


class PayrollRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "school",
            "salary_month",
            "status",
            "total_processed",
            "generated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school", "created_at", "updated_at"]


class PayrollPayslipSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True, default=None)
    salary_month = serializers.DateField(source="payroll_run.salary_month", read_only=True, default=None)

    class Meta:
        model = PayrollPayslip
        fields = [
            "id",
            "staff",
            "staff_name",
            "payroll_run",
            "salary_month",
            "present_days",
            "paid_leaves",
            "unpaid_leaves",
            "gross_earnings",
            "total_deductions",
            "net_salary",
            "component_breakdown",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "salary_month", "created_at", "updated_at"]
