from .models import *
from rest_framework import serializers

class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = '__all__'
        read_only_fields = ['school']
        
        
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
    leave_type_name = serializers.CharField(
        source="leave_type.name", read_only=True
    )
    class Meta:
        model = LeaveRequest
        fields = ["id","start_date","end_date", "total_days","reason", "created_at", "updated_at","school", "staff","leave_type","leave_type_name",]
        read_only_fields = ["school", "staff", "total_days", "approved_by"]

    def create(self, validated_data):
        start_date = validated_data.get("start_date")
        end_date = validated_data.get("end_date")
        school = self.context.get("request").user.school
        user = self.context.get("request").user

        if end_date < start_date:
            raise serializers.ValidationError("End date cannot be before start date.")

        # ✅ calculate total days
        total_days = (end_date - start_date).days + 1
        validated_data["total_days"] = total_days
        validated_data["school"] = school

        staff = Staff.objects.filter(user=user, school=school).first()
        validated_data["staff"] = staff

        # ✅ create main LeaveRequest first
        leave_request = LeaveRequest.objects.create(**validated_data)

        # ✅ now create LeavePerDay entries
        current = start_date
        while current <= end_date:
            LeavePerDay.objects.create(
                school=school,
                leave=leave_request,  # ✅ correct instance
                date=current,  # store as DateField (recommended)
            )
            current += timedelta(days=1)

        return leave_request



class StaffRemainingLeaveSerializer(serializers.ModelSerializer):
    leave_type = serializers.CharField(
        source="leave_template.leave_type", read_only=True
    )
    staff_name = serializers.CharField(source="staff.name", read_only=True)
    
    class Meta:
        model = StaffRemainingLeave
        fields = ["id", "staff", "staff_name", "leave_type", "total_levaes", "remaining_leaves", ]
        read_only_fields = ["id"]



class GetLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["id", "date", "school", "leave", "status", "approved_at"]
        read_only_fields = ["id", "date", "school", "leave"]



class GetLeaveRequestSerializer(serializers.ModelSerializer):
    leave_days = GetLeavePerDaySerializer(many=True, read_only=True)
    remaining_leaves = serializers.SerializerMethodField()
    leave_type_name = serializers.CharField(
        source="leave_type.name", read_only=True
    )
    
    staff_name = serializers.CharField(source="staff.name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "staff",
            "staff_name",
            "leave_type",
            "leave_type_name",
            "reason",
            "total_days",
            "start_date",
            "end_date",
            "created_at",
            "updated_at",
            "leave_days",
            "remaining_leaves",
        ]
        read_only_fields = [
            "school",
            "staff",
            "leave_type",
            "total_days",
            "leave_days",
            "remaining_leaves",
        ]

    def get_remaining_leaves(self, obj):
        queryset = StaffRemainingLeave.objects.filter(
            staff=obj.staff, school=obj.school
        )
        return StaffRemainingLeaveSerializer(queryset, many=True).data


from django.db.models import F


class ChangeLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["status"]

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

        # ✅ Check if status is already in a final state
        if instance.status in ["CANCELLED"]:
            raise serializers.ValidationError(
                f"Cannot change status from {instance.status}. This leave is already finalized."
            )

        # ✅ Check invalid transitions
        if instance.status == "REJECTED" and new_status in ["APPROVED"]:
            raise serializers.ValidationError("Cannot approve a rejected leave.")

        # ✅ If changing to APPROVED, validate remaining leaves
        if new_status == "APPROVED" and instance.status != "APPROVED":
            leave_request = instance.leave
            staff = leave_request.staff
            leave_type = leave_request.leave_type

            remaining_data = StaffRemainingLeave.objects.filter(
                leave_template__leave_type=leave_type, staff=staff
            ).first()

            if not remaining_data:
                raise serializers.ValidationError(
                    f"No leave template found for {leave_type}."
                )

            if remaining_data.remaining_leaves <= 0:
                raise serializers.ValidationError(
                    f"Insufficient {leave_type} leaves. Remaining: {remaining_data.remaining_leaves}"
                )

        return attrs

    def update(self, instance, validated_data):
        user = self.context["request"].user
        new_status = validated_data.get("status")
        old_status = instance.status

        leave_request = instance.leave
        staff = leave_request.staff
        leave_type = leave_request.leave_type

        remaining_data = StaffRemainingLeave.objects.filter(
            leave_template__leave_type=leave_type, staff=staff
        ).first()

        # ✅ Case 1: PENDING/REJECTED → APPROVED (consume leaves)
        if new_status == "APPROVED" and old_status != "APPROVED":
            if remaining_data:
                remaining_data.remaining_leaves -= 1
                remaining_data.save()
            instance.approved_at = timezone.now()

        # ✅ Case 2: APPROVED → REJECTED/CANCELLED (restore leaves)
        elif old_status == "APPROVED" and new_status in ["REJECTED", "CANCELLED"]:
            if remaining_data:
                remaining_data.remaining_leaves += 1
                remaining_data.save()
            instance.approved_at = None

        # ✅ Case 3: Any other transition to REJECTED/CANCELLED (no leaves to restore)
        elif new_status in ["REJECTED", "CANCELLED"]:
            instance.approved_at = None

        instance.status = new_status
        instance.save()

        return instance
    
    



# class
class GetRemainingLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRemainingLeave
        fields = ["leave_template"]





class AttendanceLocationViewSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(source = "time_rule.start_time",required=True, allow_null=True)
    end_time = serializers.TimeField(source = "time_rule.end_time",required=True, allow_null=True)
    half_day_time = serializers.TimeField(source = "time_rule.half_day_time", required=False, allow_null=True)

    class Meta:
        model = AttendanceLocation
        fields = [
            "id",
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
        read_only_fields = ['school']    
        
        
        
class CertificateRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = CertificateRequest
        fields = "__all__"
        read_only_fields = ["student", "status"]
        
        
class ClerkCertificateRequestSerializer(serializers.ModelSerializer):
    # student_name = serializers.CharField(source="student.user.username", read_only=True)
    certificate_type_name = serializers.CharField(source="certificate_type.name", read_only=True)

    class Meta:
        model = CertificateRequest
        fields = [
            "id",
            # "student",
            # "student_name",
            "certificate_type",
            "certificate_type_name",
            "status",
            "created_at",
        ]
        
    