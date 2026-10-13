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
    StaffSalaryPayment,
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
    designation = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    staff_category = serializers.CharField(source="staff.category", read_only=True, default=None)
    staff_email = serializers.CharField(source="staff.email", read_only=True, default=None)
    staff_mobile = serializers.CharField(source="staff.mobile", read_only=True, default=None)
    basic_salary = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_mode = serializers.SerializerMethodField()
    payment_date = serializers.SerializerMethodField()
    receipt_number = serializers.SerializerMethodField()
    school_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollPayslip
        fields = [
            "id",
            "staff",
            "staff_name",
            "designation",
            "department",
            "staff_category",
            "staff_email",
            "staff_mobile",
            "payroll_run",
            "salary_month",
            "basic_salary",
            "present_days",
            "paid_leaves",
            "unpaid_leaves",
            "gross_earnings",
            "total_deductions",
            "net_salary",
            "payment_status",
            "payment_mode",
            "payment_date",
            "receipt_number",
            "school_name",
            "component_breakdown",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "salary_month", "created_at", "updated_at"]

    def get_designation(self, obj):
        if not obj.staff:
            return ""
        return getattr(obj.staff, "designation", None) or getattr(obj.staff, "category", "")

    def get_department(self, obj):
        if not obj.staff:
            return ""
        dept = getattr(obj.staff, "department", None)
        return dept.name if dept else getattr(obj.staff, "category", "")

    def get_basic_salary(self, obj):
        if not obj.staff:
            return "0.00"
        return str(getattr(obj.staff, "salary", 0) or "0.00")

    def get_school_name(self, obj):
        if obj.payroll_run and obj.payroll_run.school:
            return obj.payroll_run.school.name
        if obj.staff and obj.staff.school:
            return obj.staff.school.name
        return "School Management System"

    def _get_payment(self, obj):
        if not hasattr(obj, "_cached_payment"):
            month_str = ""
            if obj.payroll_run and obj.payroll_run.salary_month:
                month_str = obj.payroll_run.salary_month.strftime("%Y-%m")
            payment = None
            if month_str and obj.staff_id:
                payment = StaffSalaryPayment.objects.filter(
                    staff_id=obj.staff_id, salary_month=month_str
                ).first()
            obj._cached_payment = payment
        return obj._cached_payment

    def get_payment_status(self, obj):
        payment = self._get_payment(obj)
        if payment and payment.payment_status:
            return payment.payment_status
        return "paid" if obj.payroll_run and obj.payroll_run.status in ["Locked", "Completed", "Paid"] else "issued"

    def get_payment_mode(self, obj):
        payment = self._get_payment(obj)
        return payment.payment_mode if payment else "offline"

    def get_payment_date(self, obj):
        payment = self._get_payment(obj)
        if payment and payment.payment_date:
            return payment.payment_date
        return obj.created_at

    def get_receipt_number(self, obj):
        payment = self._get_payment(obj)
        if payment and payment.receipt_number:
            return payment.receipt_number
        month_str = obj.payroll_run.salary_month.strftime("%Y-%m") if obj.payroll_run and obj.payroll_run.salary_month else "REC"
        return f"SAL-{month_str}-{obj.staff_id}"

