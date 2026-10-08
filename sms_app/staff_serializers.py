# pyrefly: ignore [missing-import]
from rest_framework import serializers
from .models import *
# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from .validators import validate_mobile
import numpy as np
import cv2
import cv2.data

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

    def validate_name(self, value):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters.")
        if len(value.strip()) > 100:
            raise serializers.ValidationError("Full name must not exceed 100 characters.")
        return value.strip()

    def validate_email(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Email address is required.")
        value = value.strip().lower()
        import re
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", value):
            raise serializers.ValidationError("Enter a valid email address.")
        qs = User.objects.filter(email__iexact=value)
        if self.instance and self.instance.user:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise serializers.ValidationError("Email is already registered.")
        return value

    def validate_mobile(self, value):
        value = validate_mobile(value, required=True)
        qs = User.objects.filter(mobile=value)
        if self.instance and self.instance.user:
            qs = qs.exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise serializers.ValidationError("Mobile number is already registered.")
        return value

    def validate_date_of_birth(self, value):
        if value:
            import datetime
            today = datetime.date.today()
            age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
            if age < 18:
                raise serializers.ValidationError("Staff member must be at least 18 years old.")
        return value

    def validate_joining_date(self, value):
        if value:
            if value.year < 1900:
                raise serializers.ValidationError("Enter a valid joining date.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        dob = attrs.get("date_of_birth") or (self.instance.date_of_birth if self.instance else None)
        joining = attrs.get("joining_date") or (self.instance.joining_date if self.instance else None)
        if dob and joining and joining < dob:
            raise serializers.ValidationError({"joining_date": "Joining date cannot be earlier than date of birth."})
        return attrs




class GetTeacherSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = ["id", "name", "category", "created_at"]

    def get_name(self, obj):
        if obj.name and str(obj.name).strip():
            return str(obj.name).strip()
        if obj.user:
            full = f"{obj.user.first_name or ''} {obj.user.last_name or ''}".strip()
            if full:
                return full
            if obj.user.username:
                return obj.user.username
        return f"Staff #{obj.id}"


# --------FOR MANUAL STUDENT ENRTY-------




class StaffFaceSerializer(serializers.ModelSerializer):
    class Meta:
        model=StaffFace
        fields=["id","face_image","is_enrolled",
            "created_at"
        ]
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
        fields = ["id", "staff", "leave_type", "total_leaves", "month","year","remaining_leaves",
            "created_at"
        ]
        read_only_fields = ["id"]




class GetLeavePerDaySerializer(serializers.ModelSerializer):
    class Meta:
        model = LeavePerDay
        fields = ["id", "date", "school", "leave", "status", "approved_at",
            "created_at"
        ]
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
        fields = ["status",
            "created_at"
        ]

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

            rem_leaves = remaining_data.remaining_leaves if remaining_data.remaining_leaves is not None else 0
            if rem_leaves <= 0:
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
            if remaining_data and remaining_data.remaining_leaves is not None:
                remaining_data.remaining_leaves = max(0, remaining_data.remaining_leaves - 1)
                remaining_data.save()
            instance.approved_at = timezone.now()

        # ✅ Case 2: APPROVED → REJECTED/CANCELLED (restore leaves)
        elif old_status == "APPROVED" and new_status in ["REJECTED", "CANCELLED"]:
            if remaining_data and remaining_data.remaining_leaves is not None:
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
        fields = ["leave_template",
            "created_at"
        ]


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
            "joining_date",
            # "salary",
            # "is_active",
            # "created_at",
            # "updated_at",
            "created_at"
        ]
        read_only_fields = fields


class TeacherWorkloadSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    assigned_classes_count = serializers.SerializerMethodField()

    DAY_FIELDS = [
        "max_periods_mon",
        "max_periods_tue",
        "max_periods_wed",
        "max_periods_thu",
        "max_periods_fri",
        "max_periods_sat",
    ]

    class Meta:
        model = Staff
        fields = [
            "id",
            "name",
            "email",
            "mobile",
            "category",
            "department",
            "department_name",
            "max_periods_mon",
            "max_periods_tue",
            "max_periods_wed",
            "max_periods_thu",
            "max_periods_fri",
            "max_periods_sat",
            "max_weekly_periods",
            "max_consecutive_periods",
            "assigned_classes_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "name",
            "email",
            "mobile",
            "category",
            "department",
            "department_name",
            "assigned_classes_count",
            "is_active",
            "created_at",
            "updated_at",
        ]

    def get_assigned_classes_count(self, obj):
        try:
            return obj.assignclass_set.count()
        except Exception:
            return 0

    def validate_max_weekly_periods(self, value):
        if value < 1 or value > 60:
            raise serializers.ValidationError("Max weekly periods must be between 1 and 60.")
        return value

    def validate_max_consecutive_periods(self, value):
        if value < 1 or value > 10:
            raise serializers.ValidationError("Max consecutive periods must be between 1 and 10.")
        return value

    def validate(self, attrs):
        for field in self.DAY_FIELDS:
            val = attrs.get(
                field, getattr(self.instance, field, 5) if self.instance else 5
            )
            if val is not None and (val < 0 or val > 15):
                raise serializers.ValidationError({
                    field: "Daily period limit must be between 0 and 15."
                })

        weekly = attrs.get(
            "max_weekly_periods",
            getattr(self.instance, "max_weekly_periods", 25) if self.instance else 25,
        )
        consecutive = attrs.get(
            "max_consecutive_periods",
            getattr(self.instance, "max_consecutive_periods", 3) if self.instance else 3,
        )

        daily_vals = [
            attrs.get(f, getattr(self.instance, f, 5) if self.instance else 5)
            for f in self.DAY_FIELDS
        ]
        max_daily_allowed = max(daily_vals) if daily_vals else 5
        total_daily_sum = sum(daily_vals)

        if consecutive > max_daily_allowed and max_daily_allowed > 0:
            raise serializers.ValidationError({
                "max_consecutive_periods": f"Consecutive periods limit ({consecutive}) cannot exceed highest daily periods limit ({max_daily_allowed})."
            })
        if weekly > total_daily_sum:
            raise serializers.ValidationError({
                "max_weekly_periods": f"Weekly limit ({weekly}) cannot exceed the sum of all daily limits ({total_daily_sum})."
            })
        return attrs


