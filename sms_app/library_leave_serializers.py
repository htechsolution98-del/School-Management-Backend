from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import *
from rest_framework import serializers

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = '__all__'
        read_only_fields = ["created_at", 'school']
        
        
# class LeaveTypeGenericSerializer(serializers.Serializer):
#     name = serializers.CharField()
#     school = serializers.CharField()


class LeaveTemplateSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(
        source="leave_type.name", read_only=True
    )

    class Meta:
        model = LeaveTemplate
        fields = ["id","leave_num","created_at","time_line", "school", "staff", "leave_type", "leave_type_name"]
        read_only_fields = ["school","time_line"]

    def validate_leave_num(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Leave number must be a positive integer."
            )
        return value

    # def validate_leave_type(self, value):
    #     if not value or not value.strip():
    #         raise serializers.ValidationError("Leave type cannot be empty.")
    #     return value.strip()

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError("Request user is required.")

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")

        leave_type = attrs.get("leave_type")
        time_line = attrs.get("time_line")
        staff = attrs.get("staff")

        # Check for duplicate leave templates for the same school
        if LeaveTemplate.objects.filter(
            school=school, leave_type=leave_type, staff=staff
        ).exists():
            raise serializers.ValidationError(
                "A leave template with this type and timeline already exists for this school."
            )

        return attrs

    def create(self, validated_data):
        school = self.context.get("request").user.school

        # staff_data = Staff.objects.filter(school=school.id)
        staff = validated_data["staff"]

        leave_template = LeaveTemplate.objects.create(school=school, **validated_data)

        # for staff in staff_data:
        StaffRemainingLeave.objects.create(
            school=school,
            leave_template=leave_template,
            staff=staff,
            total_levaes=validated_data.get("leave_num", 0),
            remaining_leaves=validated_data.get("leave_num", 0),
        )

        return leave_template


# ADD SERIALIZE FOR LEAVE DROWPOWN IN THROUGH LeaveTemplate MODEL
from datetime import timedelta


class LeaveRequestSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.SerializerMethodField()
    dynamic_leave_type_name = serializers.SerializerMethodField()
    available_balance = serializers.SerializerMethodField()

    dynamic_leave_type = serializers.PrimaryKeyRelatedField(
        queryset=LeaveType.objects.all(), required=False, allow_null=True
    )
    leave_type = serializers.PrimaryKeyRelatedField(
        queryset=LeaveType.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "start_date",
            "end_date",
            "total_days",
            "reason",
            "created_at",
            "updated_at",
            "school",
            "staff",
            "leave_type",
            "dynamic_leave_type",
            "leave_type_name",
            "dynamic_leave_type_name",
            "is_paid",
            "status",
            "available_balance",
        ]
        read_only_fields = [
            "school",
            "staff",
            "is_paid",
            "status",
            "available_balance",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and getattr(request.user, "school", None):
            school = request.user.school
            qs = LeaveType.objects.filter(leave_template__school=school)
            staff = Staff.objects.filter(user=request.user, school=school).first()
            if staff and getattr(staff, "leave_template", None):
                tpl_qs = qs.filter(leave_template=staff.leave_template)
                if tpl_qs.exists():
                    qs = tpl_qs
            elif staff and getattr(staff, "category", None):
                cat_qs = qs.filter(category__feature__name=staff.category)
                if cat_qs.exists():
                    qs = cat_qs
            self.fields["leave_type"].queryset = qs
            self.fields["dynamic_leave_type"].queryset = qs

    def get_leave_type_name(self, obj):
        lt = obj.dynamic_leave_type or obj.leave_type
        if lt:
            return getattr(lt, "name", None) or getattr(lt, "leave_type", None) or str(lt)
        return "Leave"

    def get_dynamic_leave_type_name(self, obj):
        return self.get_leave_type_name(obj)

    def get_available_balance(self, obj):
        if not obj.staff:
            return None
        lt = obj.dynamic_leave_type or obj.leave_type
        if not lt:
            return None
        cycle = LeaveCycle.objects.filter(
            school=obj.school,
            start_date__lte=obj.start_date,
            end_date__gte=obj.start_date,
        ).first() or LeaveCycle.objects.filter(school=obj.school, is_active=True).first()
        if not cycle:
            return None
        bal = LeaveBalance.objects.filter(
            staff=obj.staff, leave_type=lt, leave_cycle=cycle
        ).first()
        if bal:
            return float(bal.remaining)
        return float(lt.allocation_count or lt.leave_num or 0)

    def validate(self, attrs):
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError("End date cannot be before start date.")

        request = self.context.get("request")
        user = request.user if request else None
        if not user:
            raise serializers.ValidationError("Authentication required.")

        staff = Staff.objects.filter(user=user).first()
        if not staff:
            raise serializers.ValidationError("Staff profile not found for user.")

        leave_type = attrs.get("dynamic_leave_type") or attrs.get("leave_type")
        if not leave_type:
            raise serializers.ValidationError("Leave type is required.")

        # Reject overlapping date ranges or multiple leave types on the same date
        overlapping = LeaveRequest.objects.filter(
            staff=staff,
            status__in=["PENDING", "APPROVED"],
            start_date__lte=end_date,
            end_date__gte=start_date,
        )
        if self.instance:
            overlapping = overlapping.exclude(id=self.instance.id)

        if overlapping.exists():
            ol = overlapping.first()
            raise serializers.ValidationError(
                f"You already have a {ol.status.lower()} leave request ({ol.start_date} to {ol.end_date}) overlapping with this date range."
            )

        overlapping_days = LeavePerDay.objects.filter(
            leave__staff=staff,
            status__in=["PENDING", "APPROVED"],
            date__range=(start_date, end_date),
        )
        if self.instance:
            overlapping_days = overlapping_days.exclude(leave=self.instance)

        if overlapping_days.exists():
            raise serializers.ValidationError(
                f"A leave request is already pending or approved for date: {overlapping_days.first().date}."
            )

        # 1. Identify active LeaveCycle
        school = user.school or staff.school
        cycle = LeaveCycle.objects.filter(
            school=school,
            start_date__lte=start_date,
            end_date__gte=start_date,
        ).first() or LeaveCycle.objects.filter(school=school, is_active=True).first()

        if not cycle:
            cycle = LeaveCycle.objects.filter(school=school).order_by("-start_date").first()

        if not cycle:
            cycle, _ = LeaveCycle.objects.get_or_create(
                school=school,
                name=f"{start_date.year}-{start_date.year + 1}",
                defaults={
                    "start_date": date(start_date.year, 1, 1),
                    "end_date": date(start_date.year, 12, 31),
                    "is_active": True,
                }
            )

        # 2. Fetch user's LeaveBalance
        balance, _ = LeaveBalance.objects.get_or_create(
            staff=staff,
            leave_type=leave_type,
            leave_cycle=cycle,
            defaults={
                "allocated": Decimal(str(leave_type.allocation_count or leave_type.leave_num or 0)),
                "carry_forward": Decimal("0.0"),
                "used": Decimal("0.0"),
                "pending": Decimal("0.0"),
            }
        )

        # 3. Calculate available balance = (allocated + carry_forward) - (used + pending)
        available_balance = Decimal(str(balance.remaining))

        # 4. Calculate requested_days (support 0.5 for half-days)
        passed_days = attrs.get("total_days")
        if passed_days is not None and Decimal(str(passed_days)) > 0:
            requested_days = Decimal(str(passed_days))
        else:
            requested_days = Decimal((end_date - start_date).days + 1)

        # 5. Overdraft validation:
        # IF requested_days > available_balance AND the LeaveType does not explicitly allow unpaid/LOP overdrafts,
        # raise a serializers.ValidationError("Insufficient leave balance")
        if leave_type.is_paid and requested_days > available_balance:
            raise serializers.ValidationError(
                f"Insufficient leave balance. You have {available_balance} days available, but requested {requested_days} days."
            )

        attrs["_school"] = school
        attrs["_staff"] = staff
        attrs["_cycle"] = cycle
        attrs["_balance"] = balance
        attrs["_requested_days"] = requested_days

        return attrs

    def create(self, validated_data):
        start_date = validated_data.get("start_date")
        end_date = validated_data.get("end_date")
        school = validated_data.pop("_school", None)
        staff = validated_data.pop("_staff", None)
        balance = validated_data.pop("_balance", None)
        requested_days = validated_data.pop("_requested_days", None)
        validated_data.pop("_cycle", None)

        if not school or not staff or not balance or requested_days is None:
            # Fallback in case validate wasn't called directly
            request = self.context.get("request")
            user = request.user if request else None
            staff = staff or Staff.objects.filter(user=user).first()
            school = school or (user.school if user else None) or (staff.school if staff else None)
            leave_type = validated_data.get("dynamic_leave_type") or validated_data.get("leave_type")
            cycle = LeaveCycle.objects.filter(school=school, is_active=True).first()
            balance, _ = LeaveBalance.objects.get_or_create(staff=staff, leave_type=leave_type, leave_cycle=cycle)
            requested_days = Decimal(str(validated_data.get("total_days") or 1.0))

        leave_type = validated_data.get("dynamic_leave_type") or validated_data.get("leave_type")

        validated_data["school"] = school
        validated_data["staff"] = staff
        validated_data["total_days"] = requested_days
        validated_data["leave_type"] = leave_type
        validated_data["dynamic_leave_type"] = leave_type
        validated_data["is_paid"] = leave_type.is_paid
        validated_data["status"] = "PENDING"

        with transaction.atomic():
            # Immediately increment pending amount on LeaveBalance
            balance.pending = F("pending") + requested_days
            balance.save(update_fields=["pending", "updated_at"])
            balance.refresh_from_db()

            leave_request = LeaveRequest.objects.create(**validated_data)

            # Create LeavePerDay entries
            current = start_date
            while current <= end_date:
                LeavePerDay.objects.create(
                    school=school,
                    leave=leave_request,
                    date=current,
                    status="PENDING",
                )
                current += timedelta(days=1)

        return leave_request



class StaffRemainingLeaveSerializer(serializers.ModelSerializer):
    leave_type_name = serializers.CharField(source="leave_type.leave_type", read_only=True)
    leave_template_timeline = serializers.CharField(source="leave_template.time_line", read_only=True)
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    
    class Meta:
        model = StaffRemainingLeave
        fields = ["created_at", "id", "staff", "staff_name", "leave_type", "leave_type_name", "leave_template", "leave_template_timeline", "total_levaes", "remaining_leaves"]
        read_only_fields = ["id", "month", "year"]



class GetLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["created_at", "id", "date", "school", "leave", "status", "approved_at"]
        read_only_fields = ["id", "date", "school", "leave"]



class GetLeaveRequestSerializer(serializers.ModelSerializer):
    leave_days = GetLeavePerDaySerializer(many=True, read_only=True)
    remaining_leaves = serializers.SerializerMethodField()
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    leave_type_name = serializers.SerializerMethodField()
    dynamic_leave_type_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "staff",
            "staff_name",
            "leave_type",
            "dynamic_leave_type",
            "leave_type_name",
            "dynamic_leave_type_name",
            "is_paid",
            "reason",
            "total_days",
            "start_date",
            "end_date",
            "status",
            "created_at",
            "updated_at",
            "leave_days",
            "remaining_leaves",
        ]
        read_only_fields = [
            "school",
            "staff",
            "leave_type",
            "dynamic_leave_type",
            "is_paid",
            "total_days",
            "leave_days",
            "remaining_leaves",
        ]

    def get_leave_type_name(self, obj):
        if obj.dynamic_leave_type:
            return obj.dynamic_leave_type.name or obj.dynamic_leave_type.leave_type
        if obj.leave_type:
            return getattr(obj.leave_type, "leave_type", str(obj.leave_type))
        return "Casual Leave"

    def get_dynamic_leave_type_name(self, obj):
        if obj.dynamic_leave_type:
            return obj.dynamic_leave_type.name or obj.dynamic_leave_type.leave_type
        return None

    def get_status(self, obj):
        if hasattr(obj, "status") and obj.status:
            return obj.status
        first_day = obj.leave_days.first() if hasattr(obj, "leave_days") else None
        if first_day and first_day.status:
            return first_day.status
        return "PENDING"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Ensure leave_type is represented as a name string if expected by frontend
        if instance.dynamic_leave_type:
            data["leave_type"] = instance.dynamic_leave_type.name or instance.dynamic_leave_type.leave_type
        elif instance.leave_type:
            data["leave_type"] = getattr(instance.leave_type, "leave_type", str(instance.leave_type))
        return data

    def get_remaining_leaves(self, obj):
        queryset = LeaveBalance.objects.filter(staff=obj.staff).select_related("leave_type", "leave_cycle")
        if queryset.exists():
            return [
                {
                    "id": b.id,
                    "staff": b.staff_id,
                    "leave_type": b.leave_type_id,
                    "leave_type_name": b.leave_type.name or b.leave_type.leave_type,
                    "allocated": float(b.allocated),
                    "used": float(b.used),
                    "pending": float(b.pending),
                    "remaining": float(b.remaining),
                    "remaining_leaves": float(b.remaining),
                }
                for b in queryset
            ]
        old_qs = StaffRemainingLeave.objects.filter(staff=obj.staff)
        return StaffRemainingLeaveSerializer(old_qs, many=True).data
    
    
    def validate(self, attrs):
        staff = attrs.get("staff")
        leave_type = attrs.get("leave_type")

        if leave_type and staff and getattr(leave_type, "category", None) and getattr(staff, "category", None):
            if leave_type.category.feature.name != staff.category:
                raise serializers.ValidationError(
                    "This leave type is not available for the selected staff category."
                )

        return attrs


class ChangeLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["created_at", "status"]

    def validate_status(self, value):
        valid_statuses = ["PENDING", "APPROVED", "REJECTED", "CANCELLED"]
        if value not in valid_statuses:
            raise serializers.ValidationError(
                f"Invalid status. Valid options are: {', '.join(valid_statuses)}"
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError("Request user is required.")

        new_status = attrs.get("status")
        instance = self.instance

        if instance.status in ["CANCELLED"]:
            raise serializers.ValidationError(
                f"Cannot change status from {instance.status}. This leave is already finalized."
            )

        if instance.status == "REJECTED" and new_status in ["APPROVED"]:
            raise serializers.ValidationError("Cannot approve a rejected leave.")

        return attrs

    def update(self, instance, validated_data):
        user = self.context["request"].user
        new_status = validated_data.get("status")
        old_status = instance.status

        leave_request = instance.leave
        staff = leave_request.staff
        leave_type = leave_request.dynamic_leave_type or leave_request.leave_type

        # Update dynamic LeaveBalance
        cycle = LeaveCycle.objects.filter(
            school=instance.school or getattr(leave_request, "school", None),
            start_date__lte=instance.date,
            end_date__gte=instance.date,
        ).first() or LeaveCycle.objects.filter(school=instance.school or getattr(leave_request, "school", None), is_active=True).first()

        balance = LeaveBalance.objects.filter(
            staff=staff, leave_type=leave_type, leave_cycle=cycle
        ).first() if (staff and leave_type and cycle) else None

        one_day = Decimal("1.0")
        if balance:
            if new_status == "APPROVED" and old_status != "APPROVED":
                if old_status == "PENDING":
                    balance.pending = max(Decimal("0.0"), balance.pending - one_day)
                balance.used = balance.used + one_day
                balance.save(update_fields=["pending", "used", "updated_at"])
            elif old_status == "PENDING" and new_status in ["REJECTED", "CANCELLED"]:
                balance.pending = max(Decimal("0.0"), balance.pending - one_day)
                balance.save(update_fields=["pending", "updated_at"])
            elif old_status == "APPROVED" and new_status in ["REJECTED", "CANCELLED"]:
                balance.used = max(Decimal("0.0"), balance.used - one_day)
                balance.save(update_fields=["used", "updated_at"])

        # Also maintain legacy table for backward compatibility
        remaining_data = StaffRemainingLeave.objects.filter(
            leave_type=leave_type, staff=staff
        ).first()
        if remaining_data:
            current_rem = remaining_data.remaining_leaves or 0
            if new_status == "APPROVED" and old_status != "APPROVED":
                if current_rem > 0:
                    remaining_data.remaining_leaves = current_rem - 1
                    remaining_data.save()
            elif old_status == "APPROVED" and new_status in ["REJECTED", "CANCELLED"]:
                remaining_data.remaining_leaves = current_rem + 1
                remaining_data.save()

        if new_status == "APPROVED":
            instance.approved_at = timezone.now()
        elif new_status in ["REJECTED", "CANCELLED"]:
            instance.approved_at = None

        instance.status = new_status
        instance.save()

        # Sync parent LeaveRequest status
        if leave_request:
            all_days = leave_request.leave_days.all()
            if all_days.exists():
                statuses = set(d.status for d in all_days)
                if len(statuses) == 1:
                    parent_status = list(statuses)[0]
                elif "APPROVED" in statuses and ("REJECTED" in statuses or "PENDING" in statuses):
                    parent_status = "PARTIAL"
                else:
                    parent_status = "PENDING"
                leave_request.status = parent_status
                leave_request.save()

        return instance
    
    



# class
class GetRemainingLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRemainingLeave
        fields = ["created_at", "leave_template"]





class AttendanceLocationViewSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(source = "time_rule.start_time",required=True, allow_null=True)
    end_time = serializers.TimeField(source = "time_rule.end_time",required=True, allow_null=True)
    half_day_time = serializers.TimeField(source = "time_rule.half_day_time", required=False, allow_null=True)

    class Meta:
        model = AttendanceLocation
        fields = ["created_at", "id",
            "latitude",
            "longitude",
            "radius",
            "school",
            "start_time",
            "end_time",
            "half_day_time",
        ]
        read_only_fields = ["school"]

    def validate(self, attrs):
        request = self.context.get("request")
        school = request.user.school

        # if this is CREATE only (not update)
        if self.instance is None:
            if AttendanceLocation.objects.filter(school=school).exists():
                raise serializers.ValidationError(
                    {"message": "You already added school attendance location"}
                )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError("Request user is required.")

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")
        
        # print("validated data..........", validated_data)
        time_rule_data = validated_data.pop("time_rule", None)
        start_time = time_rule_data.get("start_time") if time_rule_data else None
        end_time = time_rule_data.get("end_time") if time_rule_data else None
        half_day_time = time_rule_data.get("half_day_time") if time_rule_data else None
        
        # start_time = validated_data.pop("start_time", None)
        # end_time = validated_data.pop("end_time", None)
        # half_day_time = validated_data.pop("half_day_time", None)
        

        rule = AttendanceTimeRule.objects.create(
            school=school,
            start_time=start_time,
            end_time=end_time,
            half_day_time=half_day_time,
        )

        
        validated_data.pop("time_rule", None)
        
        location = AttendanceLocation.objects.create(
            school=school,
            time_rule=rule,
            **validated_data
        )
        

        return location

    
    def update(self, instance, validated_data):
        request = self.context.get("request")
        school = request.user.school

        print("VALIDATED DATA:", validated_data)
        
        # extract time fields
        time_rule_data = validated_data.pop("time_rule", None)
        start_time = time_rule_data.get("start_time") if time_rule_data else None
        end_time = time_rule_data.get("end_time") if time_rule_data else None
        half_day_time = time_rule_data.get("half_day_time") if time_rule_data else None

        # update location fields normally
        print("VALIDATED DATA:", validated_data)
        
        
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        # update related time_rule
        rule = instance.time_rule

        if rule:
            if start_time is not None:
                rule.start_time = start_time
            if end_time is not None:
                rule.end_time = end_time
            if half_day_time is not None:
                rule.half_day_time = half_day_time

            rule.save()

        return instance
    


class CerificateTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateType
        fields = '__all__'
        read_only_fields = ["created_at", 'school']    
        
        
class CertificateTemplateAdminSerializer(serializers.ModelSerializer):

    certificate_type_name = serializers.CharField(source="certificate_type.name",read_only=True)

    class Meta:
        model = CertificateTemplate

        fields = [
            "id",
            "certificate_type",
            "certificate_type_name",
            "title",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "created_at"
        ]
        

class CertificateTemplateFieldAdminSerializer(serializers.ModelSerializer):

    class Meta:
        model = CertificateTemplateField

        fields = ["created_at", "id",
            "template",
            "field_name",
            "label",
            "field_type",
            "editable",
            "required",
            "default_value",
            "display_order",
        ]
        
        
class CertificateFieldOptionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    field_type = serializers.CharField()
    editable = serializers.BooleanField()
        
        

class CertificateRequestSerializer(serializers.ModelSerializer):

    certificate_type_name = serializers.CharField(source="certificate_type.name",read_only=True)

    status = serializers.CharField(read_only=True)

    class Meta:
        model = CertificateRequest
        fields = [
            "id",
            "certificate_type",
            "certificate_type_name",
            "status",
            "created_at",
        ]
        read_only_fields = [
            "status",
            "created_at",
        ]
    
    
    
class ClerkCertificateRequestSerializer(serializers.ModelSerializer):

    student_name = serializers.SerializerMethodField()

    certificate_type = serializers.CharField(
        source="certificate_type.name"
    )

    class Meta:
        model = CertificateRequest

        fields = [
            "id",
            "student_name",
            "certificate_type",
            "status",
            "created_at",
        ]

    def get_student_name(self, obj):

        student = obj.student

        return f"{student.name} {student.surname}".strip()
        
        
        
        
class CertificateTemplateFieldSerializer(serializers.ModelSerializer):

    value = serializers.SerializerMethodField("get_field_value")

    STUDENT_FIELD_MAP = {
        "surname": "surname",
        "name": "name",
        "father_name": "father_name",
        "mother_name": "mother_name",
        "gr_no": "gr_no",
        "date_of_birth": "date_of_birth",
        "admission_date": "admission_date",
        "mobile": "mobile",
        "aadhar_number": "aadhar_number",
    }

    class Meta:
        model = CertificateTemplateField
        fields = ["created_at", "field_name",
            "label",
            "field_type",
            "editable",
            "required",
            "value",
        ]

    def get_field_value(self, obj):
        student = self.context.get("student")

        field = self.STUDENT_FIELD_MAP.get(obj.field_name)

        if field:
            return getattr(student, field, "")

        return obj.default_value or ""
    
    
    

class CertificateTemplateSerializer(serializers.ModelSerializer):

    certificate_type = serializers.CharField(source="certificate_type.name")
    
    student_name = serializers.CharField(source="student.name", read_only=True)

    template_fields = serializers.SerializerMethodField()

    class Meta:
        model = CertificateRequest

        fields = ["created_at", "id",
            "certificate_type",
            "status",
            "student",
            "student_name",
            "template_fields",
        ]
        
        read_only_fields = ["student"]

    def get_template_fields(self, obj):
        try:
            template = obj.certificate_type.template
        except CertificateTemplate.DoesNotExist:
            return []

        serializer = CertificateTemplateFieldSerializer(
            template.fields.all(),
            many=True,
            context={"student": obj.student}
        )

        return serializer.data


class CertificateGenerateSerializer(serializers.Serializer):

    generated_data = serializers.DictField()
    
    
class CertificateUploadSerializer(serializers.Serializer):

    file = serializers.FileField()
    
    
class CertificateDetailSerializer(serializers.ModelSerializer):

    class Meta:

        model = Certificate

        fields = [
            "id",
            "certificate_number",
            "generated_data",
            "file",
            "created_at",
        ]
    
    
        
        
        
        
        
class NewLeaveTypeSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField(read_only=True)
 
    class Meta:
        model = LeaveType
        fields = [
            "id",
            "leave_type",
            "name",
            "code",
            "leave_template",
            "leave_num",
            "allocation_count",
            "allocation_period",
            "is_paid",
            "carry_forward",
            "max_carry_forward",
            "allow_encashment",
            "category",
            "category_name",
            "created_at",
            "is_carry_forward",
        ]
        read_only_fields = ["id", "created_at"]
 
    def get_category_name(self, obj):
        if obj.category:
            if hasattr(obj.category, "feature") and obj.category.feature:
                return obj.category.feature.name
            return getattr(obj.category, "feature_name", None)
        return "All Staff"
 
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if request and request.user:
            school = getattr(request.user, "school", None)
            if school:
                # Restrict category choices to only this school's SchoolFeature objects
                fields["category"].queryset = fields["category"].queryset.filter(school=school)
                fields["leave_template"].queryset = fields["leave_template"].queryset.filter(school=school)
        return fields
 
    def validate(self, attrs):
        instance = self.instance
        leave_template = attrs.get("leave_template") or (instance.leave_template if instance else None)
        leave_type     = attrs.get("leave_type")     or (instance.leave_type     if instance else None)
        category       = attrs.get("category")       or (instance.category       if instance else None)
 
        if leave_template:
            qs = LeaveType.objects.filter(
                leave_template=leave_template,
                leave_type=leave_type,
                category=category,
            )
            if instance:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A leave type with this name already exists for the given template and category."
                )
        return attrs
    
    
    def create(self, validated_data):
 
        leave_type_obj = LeaveType.objects.create(**validated_data)
 
        school        = leave_type_obj.leave_template.school if leave_type_obj.leave_template else None
        category_name = leave_type_obj.category.feature.name.upper() if leave_type_obj.category else None
 
        if school and category_name:
            now      = timezone.now()
            staff_qs = Staff.objects.filter(school=school, category=category_name, is_active=True)
 
            StaffRemainingLeave.objects.bulk_create(
                [
                    StaffRemainingLeave(
                        school=school,
                        staff=staff,
                        leave_template=leave_type_obj.leave_template,
                        leave_type=leave_type_obj,
                        total_levaes=leave_type_obj.leave_num,
                        remaining_leaves=leave_type_obj.leave_num,
                        month=now.month,
                        year=now.year,
                    )
                    for staff in staff_qs
                ],
                ignore_conflicts=True,
            )
 
        return leave_type_obj
 
 
class NewLeaveTemplateSerializer(serializers.ModelSerializer):
    leave_types = NewLeaveTypeSerializer(many=True, read_only=True, source="leavetype_set")
 
    class Meta:
        model = LeaveTemplate
        fields = ["created_at", "id", "name", "time_line", "is_active", "school", "leave_types"]
        read_only_fields = ["id", "school"]
 
    def validate(self, attrs):
        instance = self.instance
        time_line = attrs.get("time_line") or (instance.time_line if instance else None)
        school    = attrs.get("school")    or (instance.school    if instance else None)
 
        qs = LeaveTemplate.objects.filter(time_line=time_line, school=school)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"time_line": "A leave template with this timeline already exists for this school."}
            )
        return attrs
 
 
class LeaveTemplateBulkCreateSerializer(serializers.Serializer):
    """
    Create a LeaveTemplate and all its LeaveTypes in one shot.
 
    POST /leave-templates/bulk_create/
    {
        "time_line": "ANNUAL",
        "leave_types": [
            {"leave_type": "Sick Leave",   "leave_num": 20, "category": 3},
            {"leave_type": "Casual Leave", "leave_num": 12, "category": 3}
        ]
    }
    """
 
    time_line = serializers.ChoiceField(choices=LeaveTemplate.TIMELINE_CHOICES, required=False, allow_null=True)
    leave_types = NewLeaveTypeSerializer(many=True, required=False, default=list)
 
    def validate(self, attrs):
        school = self.context.get("school")
        time_line = attrs.get("time_line")
        if school and time_line and LeaveTemplate.objects.filter(time_line=time_line, school=school).exists():
            raise serializers.ValidationError(
                {"time_line": "A leave template with this timeline already exists for this school."}
            )
        return attrs
 
    def create(self, validated_data):
        leave_types_data = validated_data.pop("leave_types", [])
        school = self.context["school"]
        template = LeaveTemplate.objects.create(school=school, **validated_data)
        lt_serializer = LeaveTypeSerializer()
        for lt_data in leave_types_data:
            lt_data.pop("leave_template", None)
            lt_serializer.create({**lt_data, "leave_template": template})
        return template
    
    
    
    
class StudentAttendanceListSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentAttendance
        fields = '__all__'
        
        
class SyllabusListSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source = 'subject.name', read_only = True)
    divison_name = serializers.CharField(source = 'division.division', read_only = True)
    school_class = serializers.CharField(source = 'division.SchoolClass', read_only = True)
    class Meta:
        model = Syllabus
        fields = '__all__'
        
class SchoolClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolClass
        fields = '__all__'
        
        
class ExamViewSerializer(serializers.ModelSerializer):
    class_group_name = serializers.CharField(source="class_group.school_class", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    room_number = serializers.SerializerMethodField()
    seat_number = serializers.SerializerMethodField()
    building_block = serializers.SerializerMethodField()

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'subject', 'subject_name', 'exam_date', 'start_time', 'end_time', 'class_group', 'class_group_name', 'room_number', 'seat_number', 'building_block', 'created_at']
        read_only_fields = [
            "id", "class_group_name", "subject_name", "room_number",
            "seat_number", "building_block"
        ]

    def _get_allocation(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return None
        student = getattr(request.user, "student", None) or Student.objects.filter(user=request.user).first()
        if not student:
            return None
        return SeatingAllocation.objects.filter(exam=obj, student=student).select_related("room").first()

    def get_room_number(self, obj):
        alloc = self._get_allocation(obj)
        if alloc and alloc.room:
            return alloc.room.room_number
        return None

    def get_seat_number(self, obj):
        alloc = self._get_allocation(obj)
        if alloc:
            return alloc.seat_number
        return None

    def get_building_block(self, obj):
        alloc = self._get_allocation(obj)
        if alloc and alloc.room:
            return alloc.room.building_block
        return None
        
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request:
            staff = Staff.objects.filter(user=request.user).first()

            if staff:
                self.fields["subject"].queryset = Subject.objects.filter(
                    school=staff.school
                )

                self.fields["class_group"].queryset = SchoolClass.objects.filter(
                    school=staff.school
                )
                
                
    def validate(self, attrs):
        request = self.context.get("request")
        staff = Staff.objects.filter(user=request.user).first()

        if attrs["subject"].school != staff.school:
            raise serializers.ValidationError(
                {"subject": "Invalid subject for your school."}
            )

        if attrs["class_group"].school != staff.school:
            raise serializers.ValidationError(
                {"class_group": "Invalid class group for your school."}
            )

        return attrs
    
    
    
class ResultEntrySerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    marks_obtained = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, allow_null=True)
    is_absent = serializers.BooleanField(default=False)
    remarks = serializers.CharField(required=False, allow_blank=True)



class ResultBulkCreateSerializer(serializers.Serializer):
    exam = serializers.PrimaryKeyRelatedField(queryset=Exam.objects.all())
    max_marks = serializers.DecimalField(max_digits=5, decimal_places=2)
    entries = ResultEntrySerializer(many=True)

    def validate(self, attrs):
        request = self.context.get("request")
        staff = Staff.objects.filter(user=request.user).first()
        exam = attrs["exam"]

        if exam.school != staff.school:
            raise serializers.ValidationError({"exam": "Invalid exam."})

        if exam.created_by != staff:
            # adjust this check based on how you track subject-teacher assignment
            raise serializers.ValidationError({"exam": "You are not authorized for this exam."})

        valid_student_ids = set(
            Student.objects.filter(school_class=exam.class_group).values_list("id", flat=True)
        )
        for entry in attrs["entries"]:
            if entry["student"].id not in valid_student_ids:
                raise serializers.ValidationError(
                    {"entries": f"Student {entry['student'].id} is not in this class."}
                )
            if not entry["is_absent"] and entry.get("marks_obtained") is not None:
                if entry["marks_obtained"] > attrs["max_marks"]:
                    raise serializers.ValidationError(
                        {"entries": f"Marks exceed max marks for student {entry['student'].id}."}
                    )

        return attrs
    
class ResultPublishSerializer(serializers.Serializer):
    exam = serializers.PrimaryKeyRelatedField(queryset=Exam.objects.all())

    def validate_exam(self, exam):
        request = self.context.get("request")
        staff = Staff.objects.filter(user=request.user).first()

        if not staff:
            raise serializers.ValidationError("Staff profile not found.")

        if exam.school != staff.school:
            raise serializers.ValidationError("Invalid exam for your school.")

        return exam
    
# student side view

class ResultViewSerializer(serializers.ModelSerializer):
    exam_title = serializers.CharField(source="exam.title")
    subject = serializers.CharField(source="exam.subject.name",allow_null=True,read_only=True)

    class Meta:
        model = Result
        fields = ["created_at", "exam_title", "subject", "marks_obtained", "max_marks", "is_absent", "grade", "remarks"]
    

class LibrarySettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = LibrarySetting
        fields = '__all__'
        read_only_fields = ['school']


class BookCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookCategory
        fields = '__all__'
        read_only_fields = ['school']


class AuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Author
        fields = '__all__'
        read_only_fields = ['school']


class PublisherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Publisher
        fields = '__all__'
        read_only_fields = ['school']


class RackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rack
        fields = '__all__'
        read_only_fields = ['school']


class ShelfSerializer(serializers.ModelSerializer):
    rack_code = serializers.CharField(source="rack.rack_code", read_only=True)
    rack_name = serializers.CharField(source="rack.rack_name", read_only=True)

    class Meta:
        model = Shelf
        fields = '__all__'
        read_only_fields = ['school']


class BookCopySerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    rack_code = serializers.CharField(source="rack.rack_code", read_only=True, default=None)
    shelf_code = serializers.CharField(source="shelf.shelf_code", read_only=True, default=None)

    class Meta:
        model = BookCopy
        fields = '__all__'
        read_only_fields = ['school']


class BookManageSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category_ref.name", read_only=True, default=None)
    author_name = serializers.CharField(source="author_ref.name", read_only=True, default=None)
    publisher_name = serializers.CharField(source="publisher_ref.name", read_only=True, default=None)
    rack_code = serializers.CharField(source="rack.rack_code", read_only=True, default=None)
    shelf_code = serializers.CharField(source="shelf.shelf_code", read_only=True, default=None)

    class Meta:
        model = Book
        fields = '__all__'
        read_only_fields = ['school', 'available_copies', 'status', 'created_at']

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if not ret.get("category") and instance.category_ref:
            ret["category"] = instance.category_ref.name
        if not ret.get("author") and instance.author_ref:
            ret["author"] = instance.author_ref.name
        return ret


class LateBookFeesSerializer(serializers.ModelSerializer):
    class Meta:
        model = LateBookFees
        fields = '__all__'
        read_only_fields = ['school', 'created_at']


class BookIssuedSerializer(serializers.ModelSerializer):
    copy_accession_no = serializers.CharField(source="book_copy.accession_no", read_only=True, default=None)

    class Meta:
        model = BookIssued
        fields = "__all__"
        read_only_fields = [
            "school",
            "book_issued_date",
            "actual_return_date",
            "late_fees",
            "damage_fees",
            "lost_fees",
            "total_fine",
            "is_late",
            "renewal_count",
            "status",
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.book:
            ret["book_title"] = instance.book.title
            ret["book_author"] = instance.book.author or (instance.book.author_ref.name if instance.book.author_ref else "")
            ret["book_category"] = instance.book.category or (instance.book.category_ref.name if instance.book.category_ref else "")
            ret["rack_code"] = instance.book.rack.rack_code if instance.book.rack else ""
            ret["shelf_code"] = instance.book.shelf.shelf_code if instance.book.shelf else ""
        if instance.book_copy:
            ret["accession_no"] = instance.book_copy.accession_no
            ret["barcode"] = instance.book_copy.barcode
        if instance.student:
            student_display_name = f"{instance.student.name or ''} {instance.student.surname or ''}".strip()
            ret["student_name"] = student_display_name or instance.student.gr_no or f"Student #{instance.student.id}"
            ret["student_gr_no"] = instance.student.gr_no or ""
            ret["student_roll_no"] = instance.student.roll_no or ""
            ret["student_class"] = str(instance.student.school_class) if instance.student.school_class else ""
            ret["student_division"] = instance.student.division or ""
        return ret


class BookIssuedForSelfSerializer(serializers.ModelSerializer):
    copy_accession_no = serializers.CharField(source="book_copy.accession_no", read_only=True, default=None)

    class Meta:
        model = BookIssued
        fields = "__all__"
        read_only_fields = [
            "school",
            "book_issued_date",
            "actual_return_date",
            "late_fees",
            "damage_fees",
            "lost_fees",
            "total_fine",
            "is_late",
            "renewal_count",
            "status",
            "student",
            "due_date"
        ]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if instance.book:
            ret["book_title"] = instance.book.title
            ret["book_author"] = instance.book.author or (instance.book.author_ref.name if instance.book.author_ref else "")
            ret["book_category"] = instance.book.category or (instance.book.category_ref.name if instance.book.category_ref else "")
        return ret


class BookReservationSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    student_name = serializers.SerializerMethodField()
    student_gr_no = serializers.CharField(source="student.gr_no", read_only=True)

    class Meta:
        model = BookReservation
        fields = '__all__'
        read_only_fields = ['school', 'queue_number', 'reservation_date', 'status']

    def get_student_name(self, obj):
        if obj.student:
            return f"{obj.student.name or ''} {obj.student.surname or ''}".strip() or str(obj.student)
        return "Student"