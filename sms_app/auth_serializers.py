from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
User = get_user_model()

class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(required=False)

    def validate(self, data):
        email = data.get("email")
        mobile = data.get("mobile")

        if not email and not mobile:
            raise serializers.ValidationError({"message": "Provide email or mobile"})

        if email and mobile:
            raise serializers.ValidationError(
                {"message": "Provide only one (email or mobile)"}
            )

        return data




class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_null=True)
    mobile = serializers.CharField(required=False, allow_null=True)
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True)
    school_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    school_slug = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)

    def validate(self, data):
        email = data.get("email")
        mobile = data.get("mobile")
        otp = data.get("otp")

        if not email and not mobile:
            raise serializers.ValidationError({"message": "Provide email or mobile"})

        if email and mobile:
            raise serializers.ValidationError({"message": "Provide only one"})

        # OTP check (safe filtering)
        query = OTP.objects.filter(otp=otp)

        if email:
            query = query.filter(email=email)
        if mobile:
            query = query.filter(mobile=mobile)

        otp_obj = query.order_by("-created_at").first()

        if not otp_obj:
            raise serializers.ValidationError({"message": "Invalid OTP"})

        data["otp_obj"] = otp_obj
        return data

    def create(self, validated_data):
        email = validated_data.get("email")
        mobile = validated_data.get("mobile")
        password = validated_data.get("password")
        otp_obj = validated_data["otp_obj"]
        school_id = validated_data.get("school_id")
        school_slug = validated_data.get("school_slug")

        # Username generation
        if email:
            base_username = email.split("@")[0][:4]
        else:
            base_username = mobile[-4:]

        username = base_username
        counter = 1

        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        # Create USER (ONLY ONE TABLE: customuser)
        school = None
        if school_id or school_slug:
            filters = {}
            if school_id:
                filters["id"] = school_id
            if school_slug:
                filters["slug"] = school_slug
            school = School.objects.filter(**filters).first()

        user = User.objects.create_user(
            username=username,
            email=email,
            mobile=mobile,
            password=password,
            school=school,
        )
        
        TempUser.objects.create(user=user, email=email) #-----------------------CREATE TEMP USER

        # Assign group (optional)
        group, _ = Group.objects.get_or_create(name="temp_user")
        user.groups.add(group)

        #  Delete OTP after success
        otp_obj.delete()

        return user




class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(required=False)
    username = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        mobile = data.get("mobile")
        password = data.get("password")

        email = email.lower().strip() if email else None
        mobile = mobile.strip() if mobile else None
        # username = username.strip() if username else None

        provided_credentials = [email, mobile]
        provided_count = sum(1 for value in provided_credentials if value)

        if provided_count == 0:
            raise serializers.ValidationError(
                {"message": "Provide email, mobile, or username"}
            )

        if provided_count > 1:
            raise serializers.ValidationError(
                {"message": "Provide only one of email, mobile, or username"}
            )

        if email:
            user = CustomUser.objects.filter(email=email).first()

        if mobile:
            user = CustomUser.objects.filter(mobile=mobile).first()
            if not user:
                user = CustomUser.objects.filter(username=mobile).first()
            if not user:
                school = School.objects.filter(code=mobile).first()
                if school and school.login_id:
                    user = school.login_id

        if not user or not user.check_password(password):
            raise serializers.ValidationError({"message": "Invalid credentials"})

        if not user.is_active:
            raise serializers.ValidationError({"message": "Account disabled"})

        school = getattr(user, "school", None)
        if school and school.is_active is False:
            raise serializers.ValidationError(
                {"message": "School is deactivated. Contact administrator."}
            )

        data["user"] = user
        return data




class CustomeLoginSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        
        # Check if user's school is active (skip for superadmin users without school)
        if hasattr(user, 'school') and user.school and not user.school.is_active:
            raise serializers.ValidationError({"message": "School is deactivated. Contact administrator."})

        # =====================================
        # Roles
        # =====================================
        roles = list(user.groups.values_list("name", flat=True))
        if not roles and getattr(user, "role", None):
            roles = [user.role]
        if not roles:
            roles = ["temp_user"]

        data["roles"] = roles

        return data


# ----------FOR ADD FEATURE BY SUPER USER------------




class UserListSerialzer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"




class TempUserListSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    mobile = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = TempUser
        fields = ["id", "username", "email", "mobile", "is_active"]

    def get_mobile(self, obj):
        return obj.user.mobile if obj.user else None

    def get_email(self, obj):
        return obj.email or (obj.user.email if obj.user else None)

    def get_is_active(self, obj):
        return obj.user.is_active if obj.user else False




class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = "__all__"




class ChangeModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserModuleAccess
        fields = "__all__"




