# pyrefly: ignore [missing-import]
from rest_framework import serializers
from .models import *
# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
import numpy as np
import cv2

User = get_user_model()
class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = "__all__"
        read_only_fields = ["school"]

class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = "__all__"
        read_only_fields = ["user", "school"]

    def validate_email(self, value):
        qs = User.objects.filter(email=value)
        if self.instance and self.instance.user:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise serializers.ValidationError({"message": "Email is already exists."})
        return value

    def validate_mobile(self, value):
        qs = User.objects.filter(mobile=value)
        if self.instance and self.instance.user:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise serializers.ValidationError({"message": "Mobile number is already exists."})
        return value




class GetTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = ["id", "name"]


# --------FOR MANUAL STUDENT ENRTY-------




class StaffFaceSerializer(serializers.ModelSerializer):
    class Meta:
        model=StaffFace
        fields=["id","face_image","is_enrolled"]
        read_only_fields=["is_enrolled"]
      
    def validate_face_image(self, image):
        image_bytes = np.asarray(bytearray(image.read()), dtype=np.uint8)

        img = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)

        if img is None:
            raise serializers.ValidationError(
                "Invalid image file."
            )

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        # Multi-cascade fallback for robust face detection
        cascades = [
            cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"),
            cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml"),
            cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt.xml"),
        ]

        faces = []
        for cascade in cascades:
            if not cascade.empty():
                detected = cascade.detectMultiScale(
                    gray,
                    scaleFactor=1.08,
                    minNeighbors=3,
                    minSize=(30, 30)
                )
                if len(detected) > 0:
                    faces = detected
                    break

        if len(faces) == 0:
            raise serializers.ValidationError(
                "No face detected. Please ensure your face is clearly visible and well-lit."
            )

        if len(faces) > 1:
            raise serializers.ValidationError(
                "Multiple faces detected. Please ensure only one face is visible."
            )

        image.seek(0)

        return image
    
    def create(self, validated_data):
            request = self.context["request"]
            staff = self.context.get("staff") or Staff.objects.filter(user=request.user).first()
            if not staff:
                raise serializers.ValidationError({"error": "Staff profile not found for this user"})

            face, created = StaffFace.objects.get_or_create(
                staff=staff,
                defaults=validated_data
            )

            if not created:
                face.face_image = validated_data["face_image"]
                
            face.is_enrolled = True 
            face.save()

            return face

# class ParentCreateSerializer(serializers.Serializer):
#     username = serializers.CharField()
#     email = serializers.EmailField()
#     password = serializers.CharField(write_only=True)

#     def create(self, validated_data):

#         user = User.objects.create_user(
#             username=validated_data["username"],
#             email=validated_data["email"],
#             password=validated_data["password"],
#         )

        # parent = Perents.objects.create(
        #     user=user
        # )

#         return parent



class StaffFaceVerifySerializer(serializers.Serializer):
    image=serializers.ImageField()
    


class LeaveTemplateSerializer(serializers.ModelSerializer):

    class Meta:
        model = LeaveTemplate
        fields = "__all__"
        read_only_fields = ["school"]

    def validate_leave_num(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Leave number must be greater than zero."
            )
        return value

    def validate_leave_type(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "Leave type cannot be empty."
            )
        return value.strip()

    def validate(self, attrs):
        request = self.context.get("request")

        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError(
                "Request user is required."
            )

        school = getattr(request.user, "school", None)

        if not school:
            raise serializers.ValidationError(
                "User school is not configured."
            )

        staff = attrs.get("staff")
        leave_type = attrs.get("leave_type")
        time_line = attrs.get("time_line")

        qs = LeaveTemplate.objects.filter(
            school=school,
            staff=staff,
            leave_type=leave_type,
            time_line=time_line,
        )

        # Ignore current record during update
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "This leave template already exists for this staff."
            )

        return attrs

    def create(self, validated_data):
        school = self.context["request"].user.school

        leave_template = LeaveTemplate.objects.create(
            # school=school,
            **validated_data
        )

        StaffRemainingLeave.objects.create(
            school=school,
            staff=leave_template.staff,
            leave_template=leave_template,
            month=timezone.now().month,
            year=timezone.now().year,
            total_leaves=leave_template.leave_num,
            remaining_leaves=leave_template.leave_num,
        )

        return leave_template


# ADD SERIALIZE FOR LEAVE DROWPOWN IN THROUGH LeaveTemplate MODEL
from datetime import timedelta




class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = "__all__"
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

    class Meta:
        model = StaffRemainingLeave
        fields = ["id", "staff", "leave_type", "total_leaves", "month","year","remaining_leaves"]
        read_only_fields = ["id"]




class GetLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["id", "date", "school", "leave", "status", "approved_at"]
        read_only_fields = ["id", "date", "school", "leave"]




class GetLeaveRequestSerializer(serializers.ModelSerializer):
    leave_days = GetLeavePerDaySerializer(many=True, read_only=True)
    remaining_leaves = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "staff",
            "leave_type",
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


# pyrefly: ignore [missing-import]
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


class BulkLeaveStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED"]
    )


# class


class GetRemainingLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRemainingLeave
        fields = ["leave_template"]


class StaffListSirializer(serializers.ModelSerializer):
    # user_id = serializers.IntegerField(source="user.id", read_only=True)
    # school_name = serializers.CharField(source="school.name", read_only=True)

    class Meta:
        model = Staff
        fields = [
            "id",
            # "user_id",
            # "school",
            # "school_name",
            "name",
            # "email",
            # "mobile",
            "category",
            # "address",
            # "date_of_birth",
            # "joining_date",
            # "salary",
            # "is_active",
            # "created_at",
            # "updated_at",
        ]
        read_only_fields = fields
