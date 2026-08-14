from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers
from decimal import Decimal
from .models import *
import re

class RazarDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = RazorPayData
        fields = "__all__"
        # read_only_fields = ['school/']

    def validate(self, attrs):
        school = attrs.get("school")

        if RazorPayData.objects.filter(school=school).exists():
            raise serializers.ValidationError(
                {"meassage": "This School Razor Pay Data Already Added"}
            )
        return attrs




class FeeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeType
        fields = "__all__"
        read_only_fields = ["school"]

    def normalize_fee_name(self, name):
        words = re.findall(r"[a-z0-9]+", name.lower())
        normalized_words = []

        for word in words:
            if word.endswith("ies") and len(word) > 3:
                word = f"{word[:-3]}y"
            elif word.endswith("s") and len(word) > 3:
                word = word[:-1]
            normalized_words.append(word)

        return " ".join(normalized_words)

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        billing_cycle = attrs.get(
            "billing_cycle", getattr(self.instance, "billing_cycle", None)
        )
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None

        if not name or not str(name).strip():
            raise serializers.ValidationError({"name": "Fee type name is required."})

        normalized_name = self.normalize_fee_name(str(name).strip())
        queryset = FeeType.objects.filter(school=school, billing_cycle=billing_cycle)

        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        for fee_type in queryset:
            if self.normalize_fee_name(fee_type.name or "") == normalized_name:
                raise serializers.ValidationError(
                    {"name": "This fee type already exists for this billing cycle."}
                )

        return attrs



class FeeWiseClassSerializer(serializers.ModelSerializer):
    feetype_name = serializers.CharField(source="feetype.name", read_only=True)
    billing_cycle = serializers.CharField(source="feetype.billing_cycle", read_only=True)
    school_class_name = serializers.CharField(
        source="school_class.school_class", read_only=True
    )

    class Meta:
        model = FeeWiseClass
        fields = [
            "id",
            "school",
            "feetype",
            "feetype_name",
            "billing_cycle",
            "school_class",
            "school_class_name",
            "amount",
            "late_fee_enabled",
            "grace_days",
            "late_fee_type",
            "late_fee_amount",
            "max_late_fee",
        ]
        read_only_fields = ["school", "feetype_name", "billing_cycle", "school_class_name"]

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        feetype = attrs.get("feetype", getattr(self.instance, "feetype", None))
        school_class = attrs.get(
            "school_class", getattr(self.instance, "school_class", None)
        )

        if school and feetype and feetype.school_id != school.id:
            raise serializers.ValidationError(
                {"feetype": "Invalid fee type for this school."}
            )

        if school and school_class and school_class.school_id != school.id:
            raise serializers.ValidationError(
                {"school_class": "Invalid class for this school."}
            )

        if not feetype:
            raise serializers.ValidationError({"feetype": "Fee type is required."})

        if not school_class:
            raise serializers.ValidationError(
                {"school_class": "School class is required."}
            )

        existing = FeeWiseClass.objects.filter(
            school=school,
            feetype=feetype,
            school_class=school_class,
        )

        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise serializers.ValidationError(
                {"message": "This fee type is already configured for this class."}
            )

        late_fee_enabled = attrs.get(
            "late_fee_enabled", getattr(self.instance, "late_fee_enabled", False)
        )
        late_fee_type = attrs.get(
            "late_fee_type", getattr(self.instance, "late_fee_type", None)
        )
        late_fee_amount = attrs.get(
            "late_fee_amount",
            getattr(self.instance, "late_fee_amount", Decimal("0.00")),
        )
        max_late_fee = attrs.get(
            "max_late_fee", getattr(self.instance, "max_late_fee", None)
        )

        if late_fee_enabled and not late_fee_type:
            raise serializers.ValidationError(
                {"late_fee_type": "Late fee type is required when late fee is enabled."}
            )

        if late_fee_enabled and late_fee_amount <= 0:
            raise serializers.ValidationError(
                {"late_fee_amount": "Late fee amount must be greater than 0."}
            )

        if max_late_fee is not None and max_late_fee < 0:
            raise serializers.ValidationError(
                {"max_late_fee": "Maximum late fee cannot be negative."}
            )

        return attrs




class SalaryComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryComponent
        fields = [
            "id",
            "school",
            "name",
            "component_type",
            "is_active",
        ]
        read_only_fields = ["school"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Component name cannot be empty.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        name = attrs.get("name", getattr(self.instance, "name", None))
        component_type = attrs.get(
            "component_type", getattr(self.instance, "component_type", None)
        )

        if not school:
            raise serializers.ValidationError("User school is not configured.")

        existing = SalaryComponent.objects.filter(
            school=school,
            name__iexact=name,
            component_type=component_type,
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"message": "This salary component already exists for this school."}
            )

        return attrs




class StaffSalaryComponentSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    component_name = serializers.CharField(source="component.name", read_only=True)
    component_type = serializers.CharField(
        source="component.component_type", read_only=True
    )

    class Meta:
        model = StaffSalaryComponent
        fields = [
            "id",
            "staff",
            "staff_name",
            "component",
            "component_name",
            "component_type",
            "calculation_type",
            "value",
            "is_active",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        staff = attrs.get("staff", getattr(self.instance, "staff", None))
        component = attrs.get("component", getattr(self.instance, "component", None))
        calculation_type = attrs.get(
            "calculation_type", getattr(self.instance, "calculation_type", None)
        )
        value = attrs.get("value", getattr(self.instance, "value", None))

        if not school:
            raise serializers.ValidationError("User school is not configured.")

        if not staff:
            raise serializers.ValidationError({"staff": "Staff is required."})
        if staff.school_id != school.id:
            raise serializers.ValidationError(
                {"staff": "Invalid staff for this school."}
            )

        if not component:
            raise serializers.ValidationError(
                {"component": "Salary component is required."}
            )
        if component.school_id != school.id:
            raise serializers.ValidationError(
                {"component": "Invalid salary component for this school."}
            )

        if value is not None and value <= 0:
            raise serializers.ValidationError(
                {"value": "Value must be greater than 0."}
            )

        if calculation_type == "percentage" and value and value > 100:
            raise serializers.ValidationError(
                {"value": "Percentage value cannot be greater than 100."}
            )

        existing = StaffSalaryComponent.objects.filter(
            staff=staff,
            component=component,
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"message": "This component is already assigned to this staff."}
            )

        return attrs




class StaffSalaryPaymentSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(read_only=True)
    staff_category = serializers.CharField(read_only=True)
    paid_by_username = serializers.CharField(source="paid_by.username", read_only=True)

    class Meta:
        model = StaffSalaryPayment
        fields = [
            "id",
            "school",
            "staff",
            "staff_name",
            "staff_category",
            "salary_month",
            "basic_salary",
            "total_earnings",
            "total_deductions",
            "working_days",
            "present_days",
            "absent_days",
            "half_days",
            "attendance_deduction",
            "component_snapshot",
            "net_salary",
            "paid_amount",
            "payment_mode",
            "payment_status",
            "transaction_id",
            "receipt_number",
            "payment_date",
            "note",
            "paid_by",
            "paid_by_username",
            "working_days",
            "present_days",
            "absent_days",
            "half_days",
            "attendance_deduction",
            "component_snapshot",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "school",
            "staff_name",
            "staff_category",
            "paid_by",
            "paid_by_username",
            "created_at",
            "updated_at",
        ]

    def validate_salary_month(self, value):
        if not re.match(r"^\d{4}-\d{2}$", value):
            raise serializers.ValidationError("Salary month must be in YYYY-MM format.")

        month = int(value.split("-")[1])
        if month < 1 or month > 12:
            raise serializers.ValidationError("Salary month must be valid.")

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        staff = attrs.get("staff", getattr(self.instance, "staff", None))
        salary_month = attrs.get(
            "salary_month", getattr(self.instance, "salary_month", None)
        )
        basic_salary = attrs.get(
            "basic_salary", getattr(self.instance, "basic_salary", Decimal("0.00"))
        )
        total_earnings = attrs.get(
            "total_earnings",
            getattr(self.instance, "total_earnings", Decimal("0.00")),
        )
        total_deductions = attrs.get(
            "total_deductions",
            getattr(self.instance, "total_deductions", Decimal("0.00")),
        )
        net_salary = attrs.get("net_salary", getattr(self.instance, "net_salary", None))
        paid_amount = attrs.get(
            "paid_amount", getattr(self.instance, "paid_amount", None)
        )
        payment_mode = attrs.get(
            "payment_mode", getattr(self.instance, "payment_mode", None)
        )
        transaction_id = attrs.get(
            "transaction_id", getattr(self.instance, "transaction_id", None)
        )

        if not school:
            raise serializers.ValidationError("User school is not configured.")

        if not staff:
            raise serializers.ValidationError({"staff": "Staff is required."})
        if staff.school_id != school.id:
            raise serializers.ValidationError(
                {"staff": "Invalid staff for this school."}
            )

        for field_name, amount in [
            ("basic_salary", basic_salary),
            ("total_earnings", total_earnings),
            ("total_deductions", total_deductions),
            ("net_salary", net_salary),
            ("paid_amount", paid_amount),
        ]:
            if amount is not None and amount < 0:
                raise serializers.ValidationError(
                    {field_name: "Amount cannot be negative."}
                )

        if net_salary is None:
            raise serializers.ValidationError({"net_salary": "Net salary is required."})

        if paid_amount is None:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount is required."}
            )

        if paid_amount > net_salary:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount cannot be greater than net salary."}
            )

        if payment_mode == "online" and not transaction_id:
            raise serializers.ValidationError(
                {"transaction_id": "Transaction ID is required for online payment."}
            )

        existing = StaffSalaryPayment.objects.filter(
            staff=staff,
            salary_month=salary_month,
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(
                {"message": "Salary payment already exists for this staff and month."}
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        if not validated_data.get("payment_date"):
            validated_data["payment_date"] = timezone.now()
        if user:
            validated_data["paid_by"] = user

        return super().create(validated_data)




class GenerateStaffSalaryPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffSalaryPayment
        fields = [
            "staff",
            "salary_month",
            "payment_mode",
            "transaction_id",
            # "receipt_number",
            "payment_status",
            "payment_date",
            "note",
        ]

    def validate_salary_month(self, value):
        if not re.match(r"^\d{4}-\d{2}$", value):
            raise serializers.ValidationError("Salary month must be in YYYY-MM format.")

        month = int(value.split("-")[1])
        if month < 1 or month > 12:
            raise serializers.ValidationError("Salary month must be valid.")

        return value

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        staff = attrs.get("staff")
        payment_mode = attrs.get("payment_mode")
        transaction_id = attrs.get("transaction_id")

        if not school:
            raise serializers.ValidationError("User school is not configured.")

        if staff.school_id != school.id:
            raise serializers.ValidationError(
                {"staff": "Invalid staff for this school."}
            )

        if payment_mode == "online" and not transaction_id:
            raise serializers.ValidationError(
                {"transaction_id": "Transaction ID is required for online payment."}
            )

        if StaffSalaryPayment.objects.filter(
            staff=staff, salary_month=attrs.get("salary_month")
        ).exists():
            raise serializers.ValidationError(
                {"message": "Salary payment already exists for this staff and month."}
            )

        return attrs

    def calculate_component_amount(self, component, basic_salary):
        if component.calculation_type == "percentage":
            return (basic_salary * component.value / Decimal("100")).quantize(
                Decimal("0.01")
            )

        return component.value

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        staff = validated_data["staff"]
        salary_month = validated_data["salary_month"]
        print(salary_month)

        year, month = [int(part) for part in salary_month.split("-")]
        working_days = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, working_days)

        basic_salary = staff.salary or Decimal("0.00")
        per_day_salary = (
            basic_salary / Decimal(working_days) if working_days else Decimal("0.00")
        )

        attendance_qs = Attendance.objects.filter(
            staff=staff,
            attendance_date__gte=month_start,
            attendance_date__lte=month_end,
        )
        present_count = attendance_qs.filter(is_present=True, is_half_day=False).count()
        half_days = attendance_qs.filter(is_present=True, is_half_day=True).count()
        absent_days = max(working_days - present_count - half_days, 0)
        present_days = Decimal(present_count) + (Decimal(half_days) / Decimal("2"))
        # attendance_deduction = (
        #     (Decimal(absent_days) * per_day_salary)
        #     + (Decimal(half_days) * per_day_salary / Decimal("2"))
        # ).quantize(Decimal("0.01"))
        
        approved_paid_days = get_approved_paid_leave_days(staff, month_start, month_end)
        attendance_deduction = Decimal(approved_paid_days) * per_day_salary

        total_earnings = Decimal("0.00")
        component_deductions = Decimal("0.00")
        component_snapshot = []

        staff_components = StaffSalaryComponent.objects.filter(
            staff=staff,
            is_active=True,
            component__is_active=True,
        ).select_related("component")

        for staff_component in staff_components:
            amount = self.calculate_component_amount(staff_component, basic_salary)
            component_type = staff_component.component.component_type

            if component_type == "earning":
                total_earnings += amount
            else:
                component_deductions += amount

            component_snapshot.append(
                {
                    "component_id": staff_component.component_id,
                    "name": staff_component.component.name,
                    "component_type": component_type,
                    "calculation_type": staff_component.calculation_type,
                    "value": str(staff_component.value),
                    "amount": str(amount),
                }
            )

        total_deductions = (component_deductions + attendance_deduction).quantize(
            Decimal("0.01")
        )
        net_salary = (basic_salary + total_earnings - total_deductions).quantize(
            Decimal("0.01")
        )

        if net_salary < 0:
            net_salary = Decimal("0.00")

        receipt_number = f"SAL-{salary_month}-{user.school.id}-{user.school.slug}"
        print("RECEIPT", receipt_number, flush=True)
        # b = None
        # payment = None
        payment = StaffSalaryPayment.objects.create(
            staff=staff,
            salary_month=salary_month,
            basic_salary=basic_salary,
            total_earnings=total_earnings.quantize(Decimal("0.01")),
            total_deductions=total_deductions,
            working_days=working_days,
            present_days=present_days,
            absent_days=absent_days,
            half_days=half_days,
            attendance_deduction=attendance_deduction,
            component_snapshot=component_snapshot,
            net_salary=net_salary,
            paid_amount=net_salary,
            payment_mode=validated_data["payment_mode"],
            payment_status=validated_data.get("payment_status", "paid"),
            transaction_id=validated_data.get("transaction_id"),
            receipt_number=receipt_number,
            payment_date=validated_data.get("payment_date") or timezone.now(),
            note=validated_data.get("note"),
            paid_by=user,
        )

        return payment




class StudentFeeSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    feetype = serializers.PrimaryKeyRelatedField(
        queryset=FeeType.objects.all(), required=False
    )
    feetype_name = serializers.CharField(source="feetype.name", read_only=True)
    fee_wise_class = serializers.PrimaryKeyRelatedField(read_only=True)
    school_class = serializers.IntegerField(
        source="student.school_class_id", read_only=True
    )
    school_class_name = serializers.SerializerMethodField()
    payable_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    actual_payable_amount = serializers.DecimalField(
        source="payable_amount", max_digits=10, decimal_places=2, read_only=True
    )
    balance_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    payments = serializers.SerializerMethodField()

    class Meta:
        model = StudentFee
        fields = [
            "id",
            "school",
            "academic_year",
            "student",
            "student_name",
            "school_class",
            "school_class_name",
            "feetype",
            "feetype_name",
            "fee_wise_class",
            "billing_period",
            "amount",
            "discount_amount",
            "discount_reference",
            "discount_note",
            "late_fee_enabled",
            "grace_days",
            "late_fee_type",
            "late_fee_amount",
            "max_late_fee",
            "fine_amount",
            "paid_amount",
            "payable_amount",
            "actual_payable_amount",
            "balance_amount",
            "due_date",
            "status",
            "payment_mode",
            "transaction_id",
            "payments",
            "created_at",
            "paid_at",
        ]
        read_only_fields = [
            "school",
            "student_name",
            "school_class",
            "school_class_name",
            "feetype_name",
            "payable_amount",
            "actual_payable_amount",
            "balance_amount",
            "payments",
            "created_at",
        ]
        validators = []

    def get_student_name(self, obj):
        return " ".join(
            filter(
                None, [obj.student.surname, obj.student.name, obj.student.father_name]
            )
        )

    def get_school_class_name(self, obj):
        if obj.student and obj.student.school_class:
            return obj.student.school_class.school_class
        return None

    def get_payments(self, obj):
        payments = obj.payments.order_by("-payment_date", "-created_at")
        return StudentFeePaymentSerializer(
            payments, many=True, context=self.context
        ).data

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None

        student = attrs.get("student", getattr(self.instance, "student", None))
        academic_year = attrs.get(
            "academic_year", getattr(self.instance, "academic_year", None)
        )
        feetype = attrs.get("feetype", getattr(self.instance, "feetype", None))
        billing_period = attrs.get(
            "billing_period", getattr(self.instance, "billing_period", "")
        )

        if school and student and student.school_id != school.id:
            raise serializers.ValidationError(
                {"student": "Invalid student for this school."}
            )

        if school and academic_year and academic_year.school_id != school.id:
            raise serializers.ValidationError(
                {"academic_year": "Invalid academic year for this school."}
            )

        if not student:
            raise serializers.ValidationError({"student": "Student is required."})

        if not feetype:
            raise serializers.ValidationError({"feetype": "Fee type is required."})

        if school and feetype and feetype.school_id != school.id:
            raise serializers.ValidationError(
                {"feetype": "Invalid fee type for this school."}
            )

        if not student.school_class_id:
            raise serializers.ValidationError(
                {"student": "Student does not have a class assigned."}
            )

        fee_wise_class = FeeWiseClass.objects.filter(
            school=school,
            feetype=feetype,
            school_class_id=student.school_class_id,
        ).first()

        if not fee_wise_class:
            raise serializers.ValidationError(
                {"feetype": "This fee type is not configured for the student's class."}
            )

        attrs["fee_wise_class"] = fee_wise_class
        if attrs.get("amount") is None:
            attrs["amount"] = fee_wise_class.amount

        if feetype and feetype.billing_cycle == "monthly":
            if not billing_period:
                raise serializers.ValidationError(
                    {"billing_period": "Billing period is required for monthly fees."}
                )

            if not re.match(r"^\d{4}-\d{2}$", billing_period):
                raise serializers.ValidationError(
                    {"billing_period": "Billing period must be in YYYY-MM format."}
                )

            if academic_year and academic_year.start_month and academic_year.end_month:
                valid_periods = academic_year.get_billing_periods()
                if billing_period not in valid_periods:
                    raise serializers.ValidationError(
                        {
                            "billing_period": (
                                "Billing period must be one of this academic year's months: "
                                f"{', '.join(valid_periods)}"
                            )
                        }
                    )

            due_date = attrs.get("due_date", getattr(self.instance, "due_date", None))
            if due_date and due_date.strftime("%Y-%m") != billing_period:
                raise serializers.ValidationError(
                    {
                        "due_date": "Due date must be inside the selected billing period month."
                    }
                )

        amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0.00")))
        discount_amount = attrs.get(
            "discount_amount",
            getattr(self.instance, "discount_amount", Decimal("0.00")),
        )
        discount_reference = attrs.get(
            "discount_reference", getattr(self.instance, "discount_reference", None)
        )
        fine_amount = attrs.get(
            "fine_amount", getattr(self.instance, "fine_amount", Decimal("0.00"))
        )
        paid_amount = attrs.get(
            "paid_amount", getattr(self.instance, "paid_amount", Decimal("0.00"))
        )

        payable_amount = (amount or Decimal("0.00")) + fine_amount - discount_amount
        if discount_amount < 0:
            raise serializers.ValidationError(
                {"discount_amount": "Discount amount cannot be negative."}
            )

        if amount is not None and discount_amount > amount:
            raise serializers.ValidationError(
                {"discount_amount": "Discount cannot be greater than fee amount."}
            )

        if discount_amount > 0 and not discount_reference:
            raise serializers.ValidationError(
                {
                    "discount_reference": "Discount reference is required when discount is applied."
                }
            )

        if paid_amount > payable_amount:
            raise serializers.ValidationError(
                {"paid_amount": "Paid amount cannot be greater than payable amount."}
            )

        late_fee_enabled = attrs.get(
            "late_fee_enabled", getattr(self.instance, "late_fee_enabled", False)
        )
        late_fee_type = attrs.get(
            "late_fee_type", getattr(self.instance, "late_fee_type", None)
        )
        late_fee_amount = attrs.get(
            "late_fee_amount",
            getattr(self.instance, "late_fee_amount", Decimal("0.00")),
        )
        max_late_fee = attrs.get(
            "max_late_fee", getattr(self.instance, "max_late_fee", None)
        )

        if late_fee_enabled and not late_fee_type:
            raise serializers.ValidationError(
                {"late_fee_type": "Late fee type is required when late fee is enabled."}
            )

        if late_fee_enabled and late_fee_amount <= 0:
            raise serializers.ValidationError(
                {"late_fee_amount": "Late fee amount must be greater than 0."}
            )

        if max_late_fee is not None and max_late_fee < 0:
            raise serializers.ValidationError(
                {"max_late_fee": "Maximum late fee cannot be negative."}
            )

        existing = StudentFee.objects.filter(
            student=student,
            feetype=feetype,
            academic_year=academic_year,
            billing_period=billing_period or "",
        )
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if student and feetype and existing.exists():
            raise serializers.ValidationError(
                "This student fee already exists for this fee type, year, and period."
            )

        return attrs




class StudentFeePaymentSerializer(serializers.ModelSerializer):
    student = serializers.PrimaryKeyRelatedField(read_only=True)
    student_name = serializers.SerializerMethodField()
    student_gr_no = serializers.CharField(source="student.gr_no", read_only=True)
    student_class = serializers.SerializerMethodField()
    student_division = serializers.SerializerMethodField()
    feetype = serializers.PrimaryKeyRelatedField(read_only=True)
    feetype_name = serializers.CharField(source="feetype.name", read_only=True)
    school_name = serializers.SerializerMethodField()
    academic_year = serializers.PrimaryKeyRelatedField(
        source="student_fee.academic_year", read_only=True
    )
    academic_year_name = serializers.CharField(
        source="student_fee.academic_year.name", read_only=True
    )
    fee_billing_cycle = serializers.CharField(
        source="student_fee.feetype.billing_cycle", read_only=True
    )
    fee_amount = serializers.DecimalField(source="student_fee.amount", max_digits=10, decimal_places=2, read_only=True)
    fee_penalty = serializers.DecimalField(source="student_fee.fine_amount", max_digits=10, decimal_places=2, read_only=True)
    fee_discount = serializers.DecimalField(source="student_fee.discount_amount", max_digits=10, decimal_places=2, read_only=True)
    fee_billing_period = serializers.CharField(source="student_fee.billing_period", read_only=True)
    fee_due_date = serializers.DateField(source="student_fee.due_date", read_only=True)
    fee_payable_amount = serializers.DecimalField(
        source="student_fee.payable_amount", max_digits=10, decimal_places=2, read_only=True
    )
    fee_paid_amount = serializers.DecimalField(
        source="student_fee.paid_amount", max_digits=10, decimal_places=2, read_only=True
    )
    fee_balance_amount = serializers.DecimalField(
        source="student_fee.balance_amount", max_digits=10, decimal_places=2, read_only=True
    )
    fee_status = serializers.CharField(source="student_fee.status", read_only=True)
    collected_by_username = serializers.CharField(source="collected_by.username", read_only=True)
    verified_by_username = serializers.CharField(source="verified_by.username", read_only=True)
    balance_after_payment = serializers.SerializerMethodField()

    class Meta:
        model = StudentFeePayment
        fields = [
            "id",
            "school",
            "school_name",
            "student_fee",
            "student",
            "student_name",
            "student_gr_no",
            "student_class",
            "student_division",
            "feetype",
            "feetype_name",
            "academic_year",
            "academic_year_name",
            "fee_billing_cycle",
            "fee_amount",
            "fee_penalty",
            "fee_discount",
            "fee_billing_period",
            "fee_due_date",
            "fee_payable_amount",
            "fee_paid_amount",
            "fee_balance_amount",
            "fee_status",
            "amount",
            "payment_mode",
            "transaction_id",
            "razorpay_order_id",
            "razorpay_payment_id",
            "razorpay_signature",
            "receipt_number",
            "payment_date",
            "note",
            "collected_by",
            "collected_by_username",
            "is_verified",
            "is_bounced",
            "verified_by",
            "verified_by_username",
            "verified_at",
            "balance_after_payment",
            "created_at",
        ]
        read_only_fields = [
            "school",
            "school_name",
            "student",
            "student_name",
            "student_gr_no",
            "student_class",
            "student_division",
            "feetype",
            "feetype_name",
            "academic_year",
            "academic_year_name",
            "fee_billing_cycle",
            "fee_amount",
            "fee_penalty",
            "fee_discount",
            "fee_billing_period",
            "fee_due_date",
            "fee_payable_amount",
            "fee_paid_amount",
            "fee_balance_amount",
            "fee_status",
            "razorpay_order_id",
            "razorpay_payment_id",
            "razorpay_signature",
            "collected_by",
            "collected_by_username",
            "verified_by",
            "verified_by_username",
            "verified_at",
            "balance_after_payment",
            "created_at",
        ]

    def get_school_name(self, obj):
        return (getattr(obj.school, "name", None) or str(obj.school)) if obj.school else None

    def get_student_name(self, obj):
        return " ".join(
            filter(
                None, [obj.student.surname, obj.student.name, obj.student.father_name]
            )
        )

    def get_student_class(self, obj):
        if obj.student and obj.student.school_class:
            return obj.student.school_class.school_class
        return None

    def get_student_division(self, obj):
        if obj.student and obj.student.division:
            return obj.student.division
        return None

    def get_balance_after_payment(self, obj):
        return obj.student_fee.balance_amount

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        student_fee = attrs.get(
            "student_fee", getattr(self.instance, "student_fee", None)
        )
        amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0.00")))

        if not student_fee:
            raise serializers.ValidationError(
                {"student_fee": "Student fee is required."}
            )

        if school and student_fee.school_id != school.id:
            raise serializers.ValidationError(
                {"student_fee": "Invalid student fee for this school."}
            )

        if student_fee.status == "cancelled":
            raise serializers.ValidationError(
                {"student_fee": "Payment cannot be added for a cancelled fee."}
            )

        student_fee.apply_late_fee()

        if amount <= 0:
            raise serializers.ValidationError(
                {"amount": "Amount must be greater than 0."}
            )

        if self.instance and student_fee.pk != self.instance.student_fee_id:
            raise serializers.ValidationError(
                {
                    "student_fee": "Student fee cannot be changed after payment is created."
                }
            )

        paid_except_this = (
            student_fee.payments.filter(is_bounced=False)
            .filter(Q(is_verified=True) | ~Q(payment_mode="cheque"))
            .aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        if self.instance:
            instance_counts_as_paid = (
                not self.instance.is_bounced
                and (self.instance.is_verified or self.instance.payment_mode != "cheque")
            )
            if instance_counts_as_paid:
                paid_except_this -= self.instance.amount

        remaining_amount = student_fee.payable_amount - paid_except_this
        if amount > remaining_amount:
            raise serializers.ValidationError(
                {
                    "amount": f"Amount cannot be greater than remaining balance {remaining_amount}."
                }
            )

        payment_mode = attrs.get("payment_mode", getattr(self.instance, "payment_mode", None))
        transaction_id = attrs.get("transaction_id", getattr(self.instance, "transaction_id", None))
        if payment_mode and payment_mode.lower() in ["upi", "card"] and transaction_id:
            qs = StudentFeePayment.objects.filter(transaction_id=transaction_id)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"transaction_id": "This reference number is already used."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        if not validated_data.get("payment_date"):
            validated_data["payment_date"] = timezone.now()
        if user:
            validated_data["collected_by"] = user

        payment_mode = (validated_data.get("payment_mode") or "").lower()
        is_cheque = payment_mode == "cheque"

        payment = super().create(validated_data)
        
        payment.is_verified = not is_cheque
        if payment.is_verified and user:
            payment.verified_by = user
            payment.verified_at = timezone.now()
            
        update_fields = ["is_verified", "verified_by", "verified_at"]

        if not payment.receipt_number:
            current_year = timezone.now().year
            payment.receipt_number = f"RCPT-{current_year}-{payment.id:04d}"
            update_fields.append("receipt_number")
            
        payment.save(update_fields=update_fields)
            
        payment.student_fee.refresh_payment_status()
        return payment

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        if validated_data.get("is_verified") and not instance.is_verified and user:
            validated_data["verified_by"] = user
            validated_data["verified_at"] = timezone.now()

        payment = super().update(instance, validated_data)
        payment.student_fee.refresh_payment_status()
        return payment




class BudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model=Budget
        fields=["id","name","allocated_amount","financial_year","spent_amount","amount_left"]
        read_only_fields=["spent_amount","amount_left"]



class BudgetExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model=BudgetExpense
        fields=["id","budget","expense_type","amount","description"]



