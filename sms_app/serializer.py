import math
import calendar

from os import name

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from django.db import transaction
from rest_framework import serializers
from .models import FormField
import re
from rest_framework import serializers
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
from xml.parsers.expat import model
from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
import random
from django.contrib.auth.models import Group

from rest_framework import serializers
from django.db.models import Q, Sum
from django.contrib.auth import get_user_model
from sms_app.harsh_views import get_approved_paid_leave_days
import numpy as np
import cv2
from django.utils.timezone import now

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
    email = serializers.EmailField(required=False)
    mobile = serializers.CharField(required=False)
    otp = serializers.CharField(max_length=6)
    password = serializers.CharField(write_only=True)
    school_id = serializers.CharField(write_only=True, required=False)
    school_slug = serializers.CharField(write_only=True, required=False)

    def validate(self, data):
        email = data.get("email")
        mobile = data.get("mobile")
        otp = data.get("otp")
        school_id = data.get("school_id")
        school_slug = data.get("school_slug")

        # print(school_id)
        # print(school_slug)
        if not school_id or not school_slug:
            raise serializers.ValidationError(
                {"message": "Provide school_id or school_slug"}
            )

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
            raise serializers.ValidationError("Invalid OTP")

        data["otp_obj"] = otp_obj
        return data

    def create(self, validated_data):
        email = validated_data.get("email")
        mobile = validated_data.get("mobile")
        password = validated_data.get("password")
        otp_obj = validated_data["otp_obj"]
        school_id = validated_data.pop("school_id")
        school_slug = validated_data.pop("school_slug")

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
        school = School.objects.filter(id=school_id, slug=school_slug).first()
        user = User.objects.create_user(
            username=username,
            email=email,
            mobile=mobile,
            password=password,
            school=school,
        )
        
        TempUser.objects.create(user = user ) #-----------------------CREATE TEMP USER

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

        if not user or not user.check_password(password):
            raise serializers.ValidationError({"message": "Invalid credentials"})

        if not user.is_active:
            raise serializers.ValidationError({"message": "Account disabled"})

        data["user"] = user
        return data


class CustomeLoginSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        role = user.groups.values_list("name", flat=True)

        data["roles"] = list(role)

        return data


# ----------FOR ADD FEATURE BY SUPER USER------------


class FeatureSerialzer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = "__all__"


# -----------FOR SET WHICH FEATURE SCHOOL HAS-----------
class SchoolFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source="feature.name", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "school", "feature", "feature_name", "is_enabled"]
        read_only_fields = ["is_enabled", "feature_name"]

    def validate(self, data):
        school = data.get("school")
        feature = data.get("feature")

        if SchoolFeature.objects.filter(school=school, feature=feature).exists():
            raise serializers.ValidationError(
                {"message": "This Feature already have to this school"}
            )
        return data


# -----------TO GET FEATURE FRO DROP DOWN IN STAFF CREATE---------------
class GetFeatureSerializer(serializers.ModelSerializer):

    feature_name = serializers.CharField(source="feature.name", read_only=True)
    feature_id = serializers.CharField(source="feature.id", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["feature_id", "feature_name"]


from rest_framework import serializers


class ChangeFeatureStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolFeature
        fields = ["is_enabled"]


class SchoolFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source="feature.name", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "school", "feature", "feature_name", "is_enabled"]
        read_only_fields = ["is_enabled", "feature_name"]


class SchoolSerializer(serializers.ModelSerializer):
    feature_ids = serializers.PrimaryKeyRelatedField(
        queryset=Feature.objects.all(), many=True, write_only=True
    )
    school_features = SchoolFeatureSerializer(
        source="schoolfeature_set", many=True, read_only=True
    )

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "slug",
            "feature_ids",
            "address",
            "city",
            "state",
            "country",
            "pincode",
            "is_active",
            "school_features",
        ]
        read_only_fields = ["slug", "login_id"]

    def validate(self, data):
        email = data.get("email")
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"message": "Email is already exists."})
        return data

    def validate_feature_ids(self, value):
        ids = [f.id for f in value]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate features are not allowed.")

        return value


class SchoolListSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name"]


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


class StaffSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = "__all__"
        read_only_fields = ["user", "school"]

    def validate_email(self, value):
        if User.objects.filter(
            email=value
        ).exists():  # for filter use User model not staff model because email is in user model
            raise serializers.ValidationError({"message": "Email is already exists."})

        return value

    def validate_mobile(self, value):
        if User.objects.filter(
            mobile=value
        ).exists():  # for filter use User model not staff model because mobile is in user model
            raise serializers.ValidationError(
                {"message": "Mobile number is already exists."}
            )

        return value


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


class GetTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Staff
        fields = ["id", "name"]


# --------FOR MANUAL STUDENT ENRTY-------


class StudentExtraSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentExtraData
        fields = "__all__"


class ManualStudentSerializer(serializers.ModelSerializer):
    extra_data = StudentExtraSerializer(required=False)

    class Meta:
        model = Student
        fields = "__all__"
        read_only_fields = ["school", "user", "admission"]

    def validate(self, attrs):
        gr_no = attrs.get("gr_no")
        academic_year = attrs.get("academic_year")
        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)

        if gr_no and school:
            if Student.objects.filter(gr_no=gr_no, school=school).exists():
                raise serializers.ValidationError(
                    {
                        "gr_no": "A student with this gr_no already exists for this school."
                    }
                )

        if academic_year and school and academic_year.school_id != school.id:
            raise serializers.ValidationError(
                {"academic_year": "Invalid academic year for this school."}
            )

        return attrs

    def create(self, validated_data):

        extra_data = validated_data.pop("extra_data", None)

        student = Student.objects.create(**validated_data)

        if extra_data:
            StudentExtraData.objects.create(student=student, **extra_data)

        return student


# ===============================================


# ============FEE VERIFY BY FEE DEPARTMENT========
class AdmissionFeeVerifySerializer(serializers.ModelSerializer):

    class Meta:
        model = AdmissionFee
        fields = [
            "id",
            "amount",
            "currency",
            "payment_mode",
            "fee_verify",
            "razorpay_order_id",
            "razorpay_payment_id",
            "paid_at",
            "created_at",
        ]


# 1
class AdmissionFieldValueReadSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source="field.label", read_only=True)

    class Meta:
        model = AdmissionFieldValue
        fields = ["id", "field", "field_label", "value"]


# 2
class FeesVerifySerializer(serializers.ModelSerializer):

    # admission_number = serializers.ModelSerializer()

    field_values = AdmissionFieldValueReadSerializer(
        many=True,
        read_only=True,
        # source="field_values"
    )

    fee_data = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = [
            "id",
            "school",
            "admission_number",
            "fee_amount",
            "status",
            "fee_verified",
            "fee_verified_at",
            "field_values",
            "fee_data",
        ]

        read_only_fields = [
            "id",
            "admission_number",
            "fee_amount",
            "field_values",
            "fee_data",
        ]

    def get_fee_data(self, obj):

        fee = AdmissionFee.objects.filter(admission_number=obj.admission_number).first()

        if fee:
            return AdmissionFeeVerifySerializer(fee).data

        return None

    #  Fee verification should only update an existing admission.
    def create(self, validated_data):
        raise serializers.ValidationError(
            {
                "detail": "Fee verification does not create a new admission. Use PATCH or PUT on an existing admission."
            }
        )

    #  Get latest fee
    def update(self, instance, validated_data):

        request = self.context.get("request")

        # -------------------------------
        # UPDATE FEE STATUS
        # -------------------------------

        # instance.status = "verified"
        instance.fee_verified = True
        instance.fee_verified_at = timezone.now()
        instance.fee_verified_by = (
            request.user if request and hasattr(request, "user") else None
        )

        instance.save()

        return instance


# =====================================================

# =========ADMISSIONS PROCESS SERIALIZERS==========


class SchoolClassSerializer(serializers.ModelSerializer):

    class Meta:
        model = SchoolClass
        fields = ["id", "school_class"]

    def validate(self, data):
        request = self.context.get("request")
        school = request.user.school
        school_class = data.get("school_class")

        # Prevent duplicate in DB
        if SchoolClass.objects.filter(
            school=school, school_class__iexact=school_class
        ).exists():
            raise serializers.ValidationError(
                {"message": f"{school_class} already exists"}
            )

        return data

    def create(self, validated_data):
        request = self.context.get("request")
        school = request.user.school

        return SchoolClass.objects.create(
            school=school, school_class=validated_data["school_class"]
        )


# # ================================================ modified serializers for admission form 23/04/26


# ===================== FORMFIELD =====================
# 1
ALLOWED_STUDENT_FIELD_MAPPINGS = {
    "surname",
    "name",
    "father_name",
    "mother_name",
    "date_of_birth",
    "mobile",
    "school_class",
    "division",
    "admission_date",
    "academic_year",
    "aadhar_number",
}


class FormFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormField
        fields = [
            "id",
            "label",
            "field_type",
            "is_required",
            "options",
            "order",
            "map_to_student_field",
            "is_system_field",
        ]

    def validate_map_to_student_field(self, value):
        if value in [None, ""]:
            return value

        if value not in ALLOWED_STUDENT_FIELD_MAPPINGS:
            raise serializers.ValidationError(
                f"Invalid student field mapping '{value}'."
            )

        return value


# ===================== FORMSECTION =====================
# 2
class FormSectionSerializer(serializers.ModelSerializer):
    fields = FormFieldSerializer(many=True, required=False)

    class Meta:
        model = FormSection
        fields = ["id", "title", "order", "fields"]


# ===================== FEE STRUCTURE =====================
# 3
class AdmissionFeeStructureSerializer(serializers.ModelSerializer):
    class_name = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.all())

    class Meta:
        model = AdmissionFeeStructure
        fields = ["class_name", "fee_amount"]


class DocumentFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentField
        fields = ["id", "label", "is_required", "order"]


# ===================== MAIN SERIALIZER =====================
# 4
class AdmissionFormSerializer(serializers.ModelSerializer):
    sections = FormSectionSerializer(many=True, write_only=True, required=False)

    document_fields = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        write_only=True,
    )

    fee_structures_input = AdmissionFeeStructureSerializer(
        many=True, required=False, write_only=True
    )

    class Meta:
        model = AdmissionForm
        fields = [
            "id",
            "is_active",
            "fees_enable",
            "academic_year",
            "fees",
            "title",
            "description",
            "unique_link",
            "sections",
            "fee_type",
            "fee_structures_input",
            "document_fields",
        ]
        read_only_fields = ["unique_link"]

    # ================= VALIDATION =================
    def validate(self, data):
        fee_type = data.get("fee_type")
        fee_structures = data.get("fee_structures_input") or []

        if fee_type == "individual" and not fee_structures:
            raise serializers.ValidationError(
                "fee_structures_input is required when fee_type is 'individual'"
            )

        return data

    # ================= CREATE =================
    def create(self, validated_data):
        with transaction.atomic():

            document_fields = validated_data.pop("document_fields", [])
            sections_data = validated_data.pop("sections", [])
            fee_data = validated_data.pop("fee_structures_input", [])

            request = self.context.get("request")
            user = getattr(request, "user", None)
            school = getattr(user, "school", None)

            if not school:
                raise serializers.ValidationError(
                    "User does not have a school assigned"
                )

            validated_data["school"] = school

            # ---------------- create form ----------------
            form = AdmissionForm.objects.create(**validated_data)

            # ---------------- sections + fields ----------------
            for section_data in sections_data:
                fields_data = section_data.pop("fields", [])

                section = FormSection.objects.create(
                    form=form, school=school, **section_data
                )

                for field_data in fields_data:
                    FormField.objects.create(
                        section=section, school=school, **field_data
                    )

            # ---------------- document fields ----------------
            for label in document_fields:
                DocumentField.objects.create(form=form, school=school, label=label)
                print(label)

            # ---------------- fee structures ----------------
            if form.fee_type == "individual":
                for fee in fee_data:
                    AdmissionFeeStructure.objects.create(
                        admission_form=form, school=school, **fee
                    )

            return form


# ====THIS SERIALIZER FOR VIEW ADMISSION FORM FIELD====


class AdmissionFormViewSerializer(serializers.ModelSerializer):
    sections = FormSectionSerializer(many=True)
    school_slug = serializers.CharField(source="school.slug", read_only=True)
    fee_structures = AdmissionFeeStructureSerializer(many=True, read_only=True)
    document_fields = DocumentFieldSerializer(many=True, read_only=True)

    class Meta:
        model = AdmissionForm
        fields = [
            "id",
            "title",
            "school",
            "school_slug",
            "description",
            "sections",
            "fees_enable",
            "fee_type",
            "fees",
            "fee_structures",
            "document_fields",
        ]


# ===========================================================


class ChangeFormStatus(serializers.ModelSerializer):
    class Meta:
        model = AdmissionForm
        fields = ["is_active"]


# --------Admission Form submite serializers---------
# 1class
class AdmissionFieldValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdmissionFieldValue
        fields = ["field", "value"]


class AdmissionSubmissionSerializer(serializers.ModelSerializer):
    field_values = AdmissionFieldValueSerializer(many=True, write_only=True)

    school_class = serializers.PrimaryKeyRelatedField(
        queryset=SchoolClass.objects.all(),
        required=False,
        write_only=True,    
    )

    # allow input also
    admission_number = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
    )

    fee_type = serializers.CharField(read_only=True)
    fee_amount = serializers.IntegerField(read_only=True, allow_null=True)
    payment_status = serializers.CharField(read_only=True)

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "form",
            "school",
            "school_class",
            "field_values",
            "fee_type",
            "fee_amount",
            "payment_status",
        ]
        read_only_fields = [
            "id",
            "fee_type",
            "fee_amount",
            "payment_status",
        ]

    def validate(self, data):
        form = data["form"]
        field_values = data["field_values"]
        school_class = data.get("school_class")
        admission_number = data.get("admission_number")

        form_fields = {
            field.id: field
            for section in form.sections.all()
            for field in section.fields.all()
        }

        for item in field_values:
            field_obj = item["field"]
            valid_field = form_fields.get(field_obj.id)

            if not valid_field:
                raise serializers.ValidationError(f"Invalid field: {field_obj}")

            if valid_field.is_required and not item.get("value"):
                raise serializers.ValidationError(f"{valid_field.label} is required")

        resolved_school_class = school_class or self._extract_school_class_from_fields(
            form, field_values
        )

        if (
            resolved_school_class
            and resolved_school_class.school_id != data["school"].id
        ):
            raise serializers.ValidationError(
                "Selected class does not belong to this school"
            )

        # check existing admission by admission_number
        existing_admission = None
        if admission_number not in [None, ""]:
            existing_admission = Admission.objects.filter(
                admission_number=admission_number
            ).first()

        if existing_admission:
            if (
                existing_admission.fee_verified
                and existing_admission.fee_verified == True
            ):
                raise serializers.ValidationError(
                    "Cannot update admission after fee verification"
                )

        data["resolved_school_class"] = resolved_school_class
        data["existing_admission"] = existing_admission

        return data

    def create(self, validated_data):
        field_values_data = validated_data.pop("field_values")
        school_class = validated_data.pop("school_class", None)
        resolved_school_class = (
            validated_data.pop("resolved_school_class", None) or school_class
        )

        existing_admission = validated_data.pop("existing_admission", None)

        form = validated_data["form"]
        school = validated_data["school"]
        user = self.context["request"].user

        # =====================================================
        # CASE 1: admission_number exists -> UPDATE OLD RECORD
        # =====================================================
        if existing_admission:

            admission = existing_admission

            admission.form = form
            admission.school = school
            admission.temp_user = user
            admission.status = "pending"
            admission.save()

            # delete old field values
            admission.field_values.all().delete()

        # =====================================================
        # CASE 2: admission_number null/none -> CREATE NEW
        # =====================================================
        else:
            admission = Admission.objects.create(
                form=form,
                school=school,
                temp_user=user,
                status="pending",
            )
            school = School.objects.filter(id=school.id).first()

            first_four = school.name[:4]

            code = random.randint(1000, 9999)
            admission_number = f"{school.id}{code}-{first_four}-ADM-{admission.id:04d}"
            admission.admission_number = admission_number
            admission.save()

        # =====================================================
        # STORE FIELD VALUES
        # =====================================================
        values = []

        for item in field_values_data:
            values.append(
                AdmissionFieldValue(
                    admission=admission,
                    field=item["field"],
                    value=item.get("value"),
                )
            )

        AdmissionFieldValue.objects.bulk_create(values)

        admission._resolved_school_class = resolved_school_class
        return admission

    def _extract_school_class_from_fields(self, form, field_values):
        for item in field_values:
            field_obj = item["field"]
            raw_value = item.get("value")

            if raw_value in [None, ""]:
                continue

            if field_obj.map_to_student_field != "school_class":
                continue

            school_class = SchoolClass.objects.filter(
                id=raw_value,
                school=form.school,
            ).first()
            if school_class:
                return school_class

        return None

    def _get_school_class(self, instance):
        school_class = getattr(instance, "_resolved_school_class", None)
        if school_class:
            return school_class

        field_value = instance.field_values.filter(
            field__map_to_student_field="school_class"
        ).first()

        if not field_value or field_value.value in [None, ""]:
            return None

        return SchoolClass.objects.filter(
            id=field_value.value,
            school=instance.school,
        ).first()

    def _get_fee_amount(self, instance, school_class):
        form = instance.form
        if not form:
            return None

        if form.fee_type == "general":
            return int(form.fees) if form.fees is not None else None

        if form.fee_type == "individual" and school_class:
            fee_structure = form.fee_structures.filter(class_name=school_class).first()
            if fee_structure and fee_structure.fee_amount is not None:
                return int(fee_structure.fee_amount)

        return None

    def to_representation(self, instance):
        school_class = self._get_school_class(instance)
        fee_amount = self._get_fee_amount(instance, school_class)

        return {
            "id": instance.id,
            "admission_number": instance.admission_number,
            "form": instance.form_id,
            "school": instance.school_id,
            "school_class": school_class.id if school_class else None,
            "fee_type": instance.form.fee_type if instance.form else None,
            "fee_amount": fee_amount,
            "payment_status": "pending",
        }


# ============================================================


# ------ Admission form document submittion serializers----------


# 1
class AdmissionDocumentItemSerializer(serializers.ModelSerializer):

    class Meta:
        model = AdmissionDocument
        fields = ["document_field", "file"]


# 2
from rest_framework.exceptions import ValidationError


class AdmissionDocumentSubmissionSerializer(serializers.ModelSerializer):

    documents = AdmissionDocumentItemSerializer(many=True, write_only=True)
    admission_number = serializers.CharField(write_only=True)

    class Meta:
        model = AdmissionDocument
        fields = ["admission_number", "documents"]
        read_only_fields = ["school"]

    def validate(self, data):
        admission_number = data.get("admission_number")
        documents = data.get("documents") or []

        if not admission_number:
            raise serializers.ValidationError(
                {"message": "Admission number is required"}
            )

        if not documents:
            raise serializers.ValidationError(
                {
                    "message": (
                        "At least one document is required. Send document_field and "
                        "file, or send documents[0][document_field] and documents[0][file]."
                    )
                }
            )

        temp_user = self.context["request"].user

        admission = Admission.objects.filter(
            admission_number=admission_number, temp_user=temp_user
        ).first()

        #  ------------------------------------------------------------work baaki
        if not admission:
            raise serializers.ValidationError({"message": "Admission not found"})

        return data

    def create(self, validated_data):

        documents_data = validated_data.pop("documents")

        admission_number = validated_data.pop("admission_number")

        temp_user = self.context["request"].user

        admission = Admission.objects.filter(
            admission_number=admission_number, temp_user=temp_user
        ).first()

        # =========================
        # VALIDATION
        # =========================

        if admission.status == "completed":
            raise serializers.ValidationError(
                {"message": "Admission already completed"}
            )

        instances = []

        for doc in documents_data:

            document_field = doc["document_field"]
            file = doc["file"]

            # =========================
            # UPSERT PER DOCUMENT TYPE
            # =========================

            obj, created = AdmissionDocument.objects.update_or_create(
                admission=admission,
                document_field=document_field,
                defaults={
                    "file": file,
                    "school": admission.school,
                },
            )

            instances.append(obj)

        return instances


# -=============================UPDATE SUBMITED DATA BY CLERK ===================


# 1
class FormFieldSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FormField
        fields = ["id", "label"]


# 2
class AdmissionFieldValueViewSerializer(serializers.ModelSerializer):
    field = FormFieldSimpleSerializer(read_only=True)  # for response
    field_id = serializers.PrimaryKeyRelatedField(
        queryset=FormField.objects.all(), source="field", write_only=True
    )

    class Meta:
        model = AdmissionFieldValue
        fields = ["field", "field_id", "value"]


# 3
class AdmissionUpdateSerializer(serializers.ModelSerializer):
    field_values = AdmissionFieldValueViewSerializer(many=True, required=False)

    class Meta:
        model = Admission
        fields = ["admission_number", "field_values"]
        read_only_fields = ["admission_number"]

    def update(self, instance, validated_data):
        field_values_data = validated_data.pop("field_values", None)

        # Update simple fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Replace field values safely
        if field_values_data is not None:
            instance.field_values.all().delete()

            AdmissionFieldValue.objects.bulk_create(
                [
                    AdmissionFieldValue(
                        admission=instance, field=item["field"], value=item.get("value")
                    )
                    for item in field_values_data
                ]
            )

        instance.save()
        return instance


# ===========================================================================

#  =========UPDATE DOCUMENT BY CLERK AFTER SUBMISSION=========


class AdmissionDocumentItemSerializer(serializers.ModelSerializer):
    document_field_name = serializers.CharField(
        source="document_field.label", read_only=True
    )

    class Meta:
        model = AdmissionDocument
        fields = ["document_field", "document_field_name", "file"]


class AdmissionDocumentSerializer(serializers.ModelSerializer):
    documents = AdmissionDocumentItemSerializer(
        source="admission_documents", many=True  # related_name
    )

    class Meta:
        model = Admission
        fields = ["admission_number", "documents"]
        read_only_fields = ["admission_number"]


from django.db import transaction


class AdmissionDocumentUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Admission
        fields = []

    def update(self, instance, validated_data):

        request = self.context["request"]

        with transaction.atomic():

            i = 0

            while True:

                # documents[0][document_field]
                document_field = request.data.get(f"documents[{i}][document_field]")

                # documents[0][file]
                file = request.FILES.get(f"documents[{i}][file]")

                # stop loop when no more documents
                if not document_field:
                    break

                # skip if file missing
                if not file:
                    i += 1
                    continue

                AdmissionDocument.objects.update_or_create(
                    admission=instance,
                    document_field_id=document_field,
                    defaults={
                        "file": file,
                    },
                )

                i += 1

        return instance


# ============================================================================


# =================get submited data for tem user====================


class AdmissionFieldValueReadSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source="field.label", read_only=True)
    field_order = serializers.IntegerField(source="field.order", read_only=True)

    class Meta:
        model = AdmissionFieldValue
        fields = ["id", "field", "field_label", "field_order", "value"]


class AdmissionSectionWiseReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    order = serializers.IntegerField()
    field_values = AdmissionFieldValueReadSerializer(many=True)


class AdmissionFeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = AdmissionFee
        fields = [
            "amount",
            "currency",
            "payment_mode",
            "paid_at",
        ]


class TempUserAdmissionDataSerializer(serializers.ModelSerializer):
    sections = serializers.SerializerMethodField()
    fee_data = serializers.SerializerMethodField()

    # school_class = serializers.SerializerMethodField()

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "school",
            "form",
            "status",
            # "school_class",
            # "division",
            "pay_process",
            "sections",
            "fee_data",
        ]

    def get_sections(self, obj):
        section_map = {}

        field_values = obj.field_values.all().select_related("field", "field__section")

        for field_value in field_values:
            section = field_value.field.section

            if section.id not in section_map:
                section_map[section.id] = {
                    "id": section.id,
                    "title": section.title,
                    "order": section.order,
                    "field_values": [],
                }

            section_map[section.id]["field_values"].append(field_value)

        sections = sorted(section_map.values(), key=lambda item: item["order"])

        for section in sections:
            section["field_values"] = sorted(
                section["field_values"],
                key=lambda field_value: field_value.field.order,
            )

        return AdmissionSectionWiseReadSerializer(sections, many=True).data

    # Extract school_class from dynamic fields
    def get_fee_data(self, obj):

        fee = AdmissionFee.objects.filter(admission_number=obj.admission_number).first()

        if fee:
            return AdmissionFeeSerializer(fee).data

        return None

    def get_school_class(self, obj):
        field_value = obj.field_values.filter(
            field__map_to_student_field="school_class"
        ).first()

        return field_value.value if field_value else None

    # Extract division (if mapped)


# ============================================================




# For viewing data


class StudentFieldValueReadSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source="field.label")

    class Meta:
        model = StudentFieldValue
        fields = ["field_label", "value", "file"]


class FormSubmissionReadSerializer(serializers.ModelSerializer):
    field_values = StudentFieldValueReadSerializer(many=True)

    class Meta:
        model = Student
        fields = ["id", "created_at", "field_values"]


# Only for Post method
class SetDivisionSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(
        source="SchoolClass.get_school_class_display", read_only=True
    )

    class Meta:
        model = Division
        fields = ["id", "SchoolClass", "class_name", "division", "capacity"]


class SetDivisionListSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(
        source="SchoolClass.get_school_class_display", read_only=True
    )

    class Meta:
        model = Division
        fields = ["id", "SchoolClass", "class_name", "division", "capacity"]


# =========serializers for set division by clerk========
# NOT IN USE
import string


class DivisionSetSerilaizer(serializers.ModelSerializer):
    capacity = serializers.IntegerField(write_only=True)

    class Meta:
        model = Student
        fields = ["division", "capacity"]

    def create(self, validated_data):
        total_division = int(validated_data.pop("division"))
        capacity = validated_data.pop("capacity")

        alphabet = string.ascii_uppercase[:total_division]

        alphabet_len = len(alphabet)

        alphabet = list(string.ascii_uppercase[:alphabet_len])

        students = Student.objects.all().order_by("created_at")

        for index, student in enumerate(students):
            division = alphabet[index % alphabet_len]  # round-robin assignment
            student.division = division
            student.save()

        return students


# ==========CLERK UPDATE AND VERIFY DATA===============GET,PUT
# clerk side verify serializerfrom django.db import transaction


# =======================
# Field Value Serializer
# =======================


class AdmissionFieldValueReadSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source="field.label", read_only=True)

    class Meta:
        model = AdmissionFieldValue
        fields = ["id", "field", "field_label", "value"]


# =======================
# Document Serializer
# =======================


class AdmissionDocumentReadSerializer(serializers.ModelSerializer):
    document_label = serializers.CharField(
        source="document_field.label", read_only=True
    )

    class Meta:
        model = AdmissionDocument
        fields = ["id", "document_field", "document_label", "file"]


# =======================
# Main Serializer
# =======================


class ClerkVerifySerializer(serializers.ModelSerializer):

    field_values = AdmissionFieldValueReadSerializer(many=True, read_only=True)
    documents = AdmissionDocumentReadSerializer(many=True, read_only=True)
    gr_no = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "gr_no",
            # "school_class",
            # "division",
            # "clerk_verified",
            # "clerk_verified_at",
            "field_values",
            "documents",
        ]

    def validate(self, attrs):
        gr_no = attrs.get("gr_no")

        if User.objects.filter(username=gr_no).exists():
            raise serializers.ValidationError(
                {"meassage": "This student already created"}
            )

        return attrs

    def update(self, instance, validated_data):

        request = self.context.get("request")
        gr_no = validated_data.pop("gr_no")
        # g = instance.status
        # print(g)
        with transaction.atomic():

            # =========================
            # 1. MARK CLERK VERIFIED
            # =========================
            # instance.clerk_verified = True
            # instance.clerk_verified_at = timezone.now()
            # instance.save()

            # =========================
            # 2. CREATE STUDENT
            # =========================

            # Generate GR number
            if StudentVerify.objects.filter(
                admission_number=instance.admission_number
            ).exists():
                raise serializers.ValidationError(
                    {"message":"This Student already created"}
                )

            student = Student.objects.create(
                school=self.context["request"].user.school,
                # form=instance.form,
                # temp_user=instance.temp_user,
                # division=instance.division,
                academic_year = instance.form.academic_year,
                admission=instance,
                gr_no=gr_no,
                # details_done=True,
            )
            
            

            StudentVerify.objects.create(
                admission_number=instance.admission_number,
                gr_no=gr_no,
                student=student,
                clerk_verify=True,
            )
            # =========================
            # 3. MAP FIXED FIELDS
            # =========================

            for field_value in instance.field_values.all():

                field = field_value.field
                value = field_value.value

                if not field.map_to_student_field:
                    continue

                if field.map_to_student_field not in ALLOWED_STUDENT_FIELD_MAPPINGS:
                    raise serializers.ValidationError(
                        {
                            "message": (
                                f"Invalid student field mapping '{field.map_to_student_field}' "
                                f"on admission field '{field.label}'."
                            )
                        }
                    )

                if field.map_to_student_field == "school_class":
                    school_class = None
                    if value is not None:
                        value_str = str(value).strip()
                        if value_str.isdigit():
                            try:
                                school_class = SchoolClass.objects.get(
                                    id=int(value_str), school=student.school
                                )
                            except SchoolClass.DoesNotExist:
                                school_class = None
                        if school_class is None and value_str:
                            school_class = SchoolClass.objects.filter(
                                school=student.school,
                                school_class=value_str,
                            ).first()

                    if school_class:
                        student.school_class = school_class
                else:
                    setattr(student, field.map_to_student_field, value)

            student.save()

            # =========================
            # 4. COPY DYNAMIC FIELDS
            # =========================

            StudentFieldValue.objects.bulk_create(
                [
                    StudentFieldValue(
                        student=student,
                        field=fv.field,
                        value=fv.value,
                        form_id=instance.form,
                        school=self.context["request"].user.school,
                    )
                    for fv in instance.field_values.all()
                    if not fv.field.map_to_student_field
                ]
            )

            # =========================
            # 5. COPY DOCUMENTS
            # =========================

            DocumentFile.objects.bulk_create(
                [
                    DocumentFile(
                        student=student,
                        label=doc.document_field,
                        document=doc.file,
                        school=self.context["request"].user.school,
                        form_id=instance.form,
                    )
                    for doc in instance.documents.all()
                ]
            )

            # =========================
            # 6. CREATE USER (STUDENT)
            # =========================

            if not student.user:
                student_user = User.objects.create(username=gr_no, password = gr_no)
                # student_user.set_password(gr_no)
                
                student_user.save()

                group, _ = Group.objects.get_or_create(name="student")
                student_user.groups.add(group)
                student_user.role = "student"
                student_user.save() 

                
                # student_user = self.context["request"].user.school

                student.user = student_user
                student.save()

            # =========================
            # 7. CREATE PARENT USER

            # =========================
            school = self.context["request"].user.school
            existing_parent = None

            if instance.temp_user_id:
                existing_parent = (
                    Perents.objects.filter(
                        school=school,
                        perents_of__admission__temp_user=instance.temp_user,
                    )
                    .select_related("user")
                    .first()
                )

            parent_user = existing_parent.user if existing_parent else None

            if not parent_user:
                if instance.temp_user_id:
                    base_username = f"parent_{school.id}_{instance.temp_user_id}"
                else:
                    mobile = student.mobile or ""
                    base_username = f"parent_{school.id}_{student.id}"

                username = base_username
                counter = 1 
                while User.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                parent_user = User.objects.create(username=username)
                parent_user.set_password("123456")
                parent_user.role = "parents"
                parent_user.save()

            group, _ = Group.objects.get_or_create(name="parents")
            parent_user.groups.add(group)

            Perents.objects.get_or_create(
                school=school,
                user=parent_user,
                perents_of=student,
            )

            # =========================
            # 8. MARK ADMISSION COMPLETE
            # =========================

            instance.status = "completed"
            instance.save()

        return instance


# ====================================================================


class PrincipleVerifySerializr(serializers.ModelSerializer):
    field_values = StudentFieldValueReadSerializer(many=True, read_only=True)

    class Meta:
        model = Student
        fields = ["principle_verified", "principle_verified_at", "field_values"]


# =======set subject serializers========


class SetSubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = "__all__"
        read_only_fields = ["school"]


class SyllabusSerializer(serializers.ModelSerializer):

    class Meta:
        model = Syllabus
        fields = "__all__"
        read_only_fields = ["school"]


# NEED VALIDATION OF SAME SUBJECT AS SAME DIVISION
# --------ASSIGN CLASS-------

from rest_framework import serializers


class AssignClassSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    class_name = serializers.CharField(
        source="division.SchoolClass.school_class", read_only=True
    )
    division_name = serializers.CharField(source="division.division", read_only=True)

    class Meta:
        model = AssignClass
        fields = [
            "teacher",
            "subject",
            "subject_name",
            "division",
            "division_name",
            "class_name",
            "is_class_teacher",
        ]

        read_only_fields = ["subject_name", "division_name", "class_name"]

    def validate(self, data):
        school = self.context["request"].user.school
        division = data.get("division")
        teacher = data.get("teacher")
        is_class_teacher = data.get("is_class_teacher", False)

        if is_class_teacher:
            if AssignClass.objects.filter(
                school=school, division=division, is_class_teacher=True
            ).exists():
                raise serializers.ValidationError("Class already has class teacher")

            if AssignClass.objects.filter(
                school=school, teacher=teacher, division=division
            ).exists():
                raise serializers.ValidationError("Teacher already assigned")

        return data

    def create(self, validated_data):
        school = self.context["request"].user.school
        validated_data["school"] = school
        return super().create(validated_data)


# ----------TO GET ADMISSION DATA TO TRUSTEE----------------
class AdmissionDocumentReadSerializer(serializers.ModelSerializer):
    document_label = serializers.CharField(
        source="document_field.label", read_only=True
    )

    class Meta:
        model = AdmissionDocument
        fields = ["id", "document_field", "document_label", "file"]


class GetAdmissionDataSerializer(serializers.ModelSerializer):
    field_values = AdmissionFieldValueReadSerializer(many=True, read_only=True)
    documents = AdmissionDocumentReadSerializer(many=True, read_only=True)

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "status",
            # "created_at",   # optional (if exists)
            "field_values",
            "documents",
        ]


class ReceiptFieldValueSerializer(serializers.ModelSerializer):
    field_name = serializers.CharField(source="field.label", read_only=True)
    section_name = serializers.CharField(source="field.section.title", read_only=True)

    class Meta:
        model = AdmissionFieldValue
        fields = ["id", "field", "field_name", "section_name", "value"]


class ReceiptDocumentSerializer(serializers.ModelSerializer):
    document_name = serializers.CharField(
        source="document_field.label", read_only=True
    )

    class Meta:
        model = AdmissionDocument
        fields = ["id", "document_field", "document_name", "file", "uploaded_at"]


class ReceiptPaymentSerializer(serializers.ModelSerializer):
    payment_type = serializers.SerializerMethodField()

    class Meta:
        model = AdmissionFee
        fields = [
            "id",
            "amount",
            "currency",
            "payment_mode",
            "payment_type",
            "razorpay_order_id",
            "razorpay_payment_id",
            "fee_verify",
            "created_at",
            "paid_at",
        ]

    def get_payment_type(self, obj):
        if obj.payment_mode == "offline":
            return "cash"
        return obj.payment_mode


class AdmissionReceiptDataSerializer(serializers.ModelSerializer):
    temp_user_data = serializers.SerializerMethodField()
    field_values = ReceiptFieldValueSerializer(many=True, read_only=True)
    documents = ReceiptDocumentSerializer(many=True, read_only=True)
    payment_detail = serializers.SerializerMethodField()
    form_title = serializers.CharField(source="form.title", read_only=True)

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "status",
            "pay_process",
            "fee_amount",
            "submitted_at",
            "form",
            "form_title",
            "temp_user_data",
            "field_values",
            "documents",
            "payment_detail",
        ]

    def get_temp_user_data(self, obj):
        if not obj.temp_user:
            return None

        return {
            "id": obj.temp_user.id,
            "username": obj.temp_user.username,
            "email": obj.temp_user.email,
            "mobile": obj.temp_user.mobile,
        }

    def get_payment_detail(self, obj):
        payment = (
            AdmissionFee.objects.filter(admission_number=obj.admission_number)
            .order_by("-paid_at", "-created_at")
            .first()
        )

        if not payment:
            return None

        return ReceiptPaymentSerializer(payment).data


# =============================================================


# class Tt_daySerializer(serializers.ModelSerializer):
#     class Meta:
#         model  = Tt_day
#         fields  = ['year','day','lecture','school_class']
#         read_only_fields = ['year']


class Tt_day_timeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_day_time
        fields = "__all__"
        read_only_fields = ["day"]


class Tt_breaksSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_breaks
        fields = "__all__"
        read_only_fields = ["day"]


class Tt_slotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tt_slot
        fields = ["id", "lecture", "slot"]
        read_only_fields = ["id", "lecture"]


class SetTimeTableSerializer(serializers.ModelSerializer):
    year_value = serializers.CharField(source="year.year", read_only=True)
    division_name = serializers.CharField(source="class_div.division", read_only=True)
    class_name = serializers.CharField(
        source="class_div.SchoolClass.school_class", read_only=True
    )
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)

    class Meta:
        model = Time_table
        fields = [
            "id",
            "year",
            "year_value",
            "day",
            "class_div",
            "division_name",
            "class_name",
            "teacher",
            "teacher_name",
            "slot",
            "start",
            "end",
        ]


from django.db import transaction


class Tt_yearSerializer(serializers.ModelSerializer):
    start_year = serializers.IntegerField(write_only=True)
    end_year = serializers.IntegerField(write_only=True)

    class Meta:
        model = Tt_year
        fields = ["year", "start_year", "end_year"]

        read_only_fields = ["year"]

    def validate(self, data):
        start = data.get("start_year")
        end = data.get("end_year")

        if len(str(start)) != 4 or len(str(end)) != 4:
            raise serializers.ValidationError("Year must be 4 digits")

        if not (1900 <= start <= 2100):
            raise serializers.ValidationError(
                "Start year must be between 1900 and 2100"
            )

        if not (1900 <= end <= 2100):
            raise serializers.ValidationError("End year must be between 1900 and 2100")

        if end != start + 1:
            raise serializers.ValidationError("End year must be start_year + 1")

        return data

    def create(self, validated_data):
        start = validated_data.get("start_year")
        end = validated_data.get("end_year")

        year_str = f"{start}-{str(end)[-2:]}"

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)

        if Tt_year.objects.filter(year=year_str).exists():
            raise serializers.ValidationError("This academic year already exists")

        with transaction.atomic():
            tt_year = Tt_year.objects.create(year=year_str, school=school)

        return tt_year


class Time_tableSerializer(serializers.ModelSerializer):
    year = serializers.PrimaryKeyRelatedField(
        queryset=Tt_year.objects.all(), write_only=True
    )

    day = serializers.CharField(write_only=True)
    lecture = serializers.CharField(write_only=True)

    class_div = serializers.PrimaryKeyRelatedField(
        queryset=Division.objects.all(), write_only=True, required=False
    )
    division = serializers.PrimaryKeyRelatedField(
        queryset=Division.objects.all(), write_only=True, required=False
    )

    day_time = Tt_day_timeSerializer(write_only=True)
    breaks = Tt_breaksSerializer(write_only=True, many=True)
    slot = serializers.ListField(
        child=serializers.DictField(), write_only=True, required=False
    )

    class Meta:
        model = Tt_year
        fields = [
            "id",
            "year",
            "day",
            "lecture",
            "class_div",
            "division",
            "day_time",
            "breaks",
            "slot",
        ]
        # read_only_fields = ["year"]

    def validate(self, data):
        slot_data = data.get("slot", [])
        class_div = data.get("class_div") or data.get("division")
        year = data.get("year")
        day = data.get("day")

        if not class_div:
            raise serializers.ValidationError({"class_div": "This field is required."})

        if year and day and class_div:
            if Tt_day.objects.filter(
                year=year,
                day=day,
                class_div=class_div,
            ).exists():
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "This timetable already exists for the selected year, day and class division."
                        ]
                    }
                )

        for item in slot_data:
            if "slot" not in item or "start" not in item or "end" not in item:
                raise serializers.ValidationError(
                    "Each slot must have slot, start and end"
                )

        return data

    def create(self, validated_data):

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)

        year = validated_data.pop("year")
        day = validated_data.pop("day")
        lecture = validated_data.pop("lecture")
        class_div = validated_data.pop("class_div", None) or validated_data.pop(
            "division", None
        )

        day_time_data = validated_data.pop("day_time")

        breaks_data = validated_data.pop("breaks")
        slot_data = validated_data.pop("slot", [])

        with transaction.atomic():

            tt_day = Tt_day.objects.create(
                school=school,
                year=year,
                day=day,
                class_div=class_div,
                lecture=lecture,
            )

            Tt_day_time.objects.create(
                school=school,
                day=tt_day,
                start=day_time_data.get("start"),
                end=day_time_data.get("end"),
            )

            for b in breaks_data:
                Tt_breaks.objects.create(
                    day=tt_day,
                    total_breaks=b.get("total_breaks"),
                    breaks=b.get("breaks"),
                    time=b.get("time"),
                    description=b.get("description"),
                )

            for item in slot_data:
                Tt_slot.objects.create(
                    school=school,
                    day=tt_day,
                    lecture=str(item.get("slot")),
                    slot={
                        "slot": item.get("slot"),
                        "start": item.get("start"),
                        "end": item.get("end"),
                    },
                )

        self._created_day_id = tt_day.id
        return year

    def to_representation(self, instance):
        request = self.context.get("request")
        days = instance.tt_day_set.all()

        class_div = request.query_params.get("class_div") if request else None
        class_id = request.query_params.get("class_id") if request else None

        if class_div:
            days = days.filter(class_div_id=class_div)

        if class_id:
            days = days.filter(class_div__SchoolClass_id=class_id)

        if request and request.method == "POST":
            created_day_id = getattr(self, "_created_day_id", None)
            if created_day_id:
                days = days.filter(id=created_day_id)

        data = {
            "id": instance.id,
            "year": instance.year,
            "days": [
                {
                    "id": d.id,
                    "day": d.day,
                    "lecture": d.lecture,
                    "class_div": (
                        {
                            "id": d.class_div.id,
                            "division": d.class_div.division,
                            "class_id": (
                                d.class_div.SchoolClass.id
                                if d.class_div and d.class_div.SchoolClass
                                else None
                            ),
                            "class_name": (
                                d.class_div.SchoolClass.school_class
                                if d.class_div and d.class_div.SchoolClass
                                else None
                            ),
                        }
                        if d.class_div
                        else None
                    ),
                    "day_time": (
                        {
                            "id": d.tt_day_time_set.first().id,
                            "start": str(d.tt_day_time_set.first().start),
                            "end": str(d.tt_day_time_set.first().end),
                        }
                        if d.tt_day_time_set.exists()
                        else None
                    ),
                    "breaks": [
                        {
                            "id": b.id,
                            "total_breaks": b.total_breaks,
                            "breaks": b.breaks,
                            "time": b.time,
                            "description": b.description,
                        }
                        for b in d.tt_breaks_set.all()
                    ],
                    "slot": [
                        {
                            "id": s.id,
                            "lecture": s.lecture,
                            "slot": s.slot,
                        }
                        for s in d.tt_slot_set.all()
                    ],
                }
                for d in days
            ],
        }

        if request and request.method == "POST":
            return {
                "message": "Table created successfully",
                "data": data,
            }

        return data


class GetStudentVerifySerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentVerify
        fields = '__all__'
  

class GetStudentExtraDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentExtraData
        fields = '__all__'
        

class GetStudentSerializer(serializers.ModelSerializer):
    studentverify = GetStudentVerifySerializer(read_only = True)
    extradata = GetStudentExtraDataSerializer(read_only = True)
    class_name = serializers.CharField(source = "school_class.school_class")
    
    class Meta:
        model = Student
        fields = [
            "id",
            "user",
            "mobile",
            "school",
            "school_class",
            "division",
            "is_active",
            "created_at",
            "gr_no",
            "studentverify",
            "extradata"
        ]

        read_only_fields = fields


class AttendanceLocationSerializer(serializers.ModelSerializer):
    start_time = serializers.TimeField(write_only=True, required=False, allow_null=True)
    end_time = serializers.TimeField(write_only=True, required=False, allow_null=True)
    half_day_time = serializers.TimeField(
        write_only=True, required=False, allow_null=True
    )

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

        if AttendanceLocation.objects.filter(school=school).exists():
            raise serializers.ValidationError(
                {"massage": "You already add school attendance location"}
            )

        return super().validate(attrs)

    def create(self, validated_data):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError("Request user is required.")

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")

        start_time = validated_data.pop("start_time", None)
        end_time = validated_data.pop("end_time", None)
        half_day_time = validated_data.pop("half_day_time", None)

        AttendanceTimeRule.objects.create(
            school=school,
            start_time=start_time,
            end_time=end_time,
            half_day_time=half_day_time,
        )

        return AttendanceLocation.objects.create(school=school, **validated_data)


def is_inside_radius(lat1, lon1, lat2, lon2, radius_meters):
    R = 6371000

    def to_rad(deg):
        return deg * math.pi / 180

    dlat = to_rad(lat2 - lat1)
    dlon = to_rad(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(to_rad(lat1)) * math.cos(to_rad(lat2)) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.asin(math.sqrt(a))
    distance = R * c

    return distance <= radius_meters


def is_after_time(current_time, rule_time):
    return bool(rule_time and current_time > rule_time)


def is_before_time(current_time, rule_time):
    return bool(rule_time and current_time < rule_time)


class AttendanceSerializer(serializers.ModelSerializer):

    latitude = serializers.CharField(write_only=True)
    longitude = serializers.CharField(write_only=True)
    # radius = serializers.CharField(write_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "latitude",
            "longitude",
            "school",
            "staff",
            "attendance_date",
            "date_time",
            "name",
            "category",
            "is_present",
            "is_half_day",
            "check_in",
            "check_out",
        ]

        read_only_fields = [
            "id",
            "school",
            "staff",
            "attendance_date",
            "date_time",
            "name",
            "category",
            "is_present",
            "is_half_day",
            "check_in",
            "check_out",
        ]

    def validate_latitude(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Latitude must be a valid number.")
        if value < -90 or value > 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise serializers.ValidationError("Longitude must be a valid number.")
        if value < -180 or value > 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not hasattr(request, "user"):
            raise serializers.ValidationError(
                "Request user is required for attendance validation."
            )

        school = getattr(request.user, "school", None)
        if not school:
            raise serializers.ValidationError("User school is not configured.")

        attendance_location = AttendanceLocation.objects.filter(
            school=school.id
        ).first()
        if not attendance_location:
            raise serializers.ValidationError(
                "Attendance location is not configured for this school."
            )

        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            raise serializers.ValidationError(
                "Staff profile not found for current user."
            )

        today = timezone.localdate()
        attendance = Attendance.objects.filter(
            staff=staff, attendance_date=today
        ).first()
        if attendance and attendance.check_out:
            raise serializers.ValidationError(
                "Check-out has already been recorded for today."
            )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        school = request.user.school
        user = request.user

        latitude = validated_data.pop("latitude", None)
        longitude = validated_data.pop("longitude", None)

        attendance_location = AttendanceLocation.objects.filter(
            school=school.id
        ).first()

        loc_latitude = attendance_location.latitude
        loc_longitude = attendance_location.longitude
        loc_radius = attendance_location.radius

        is_inside = is_inside_radius(
            float(latitude),
            float(longitude),
            float(loc_latitude),
            float(loc_longitude),
            float(loc_radius),
        )

        if not is_inside:
            raise serializers.ValidationError(
                "You are not within the attendance radius."
            )

        staff = Staff.objects.filter(user=user).first()
        attendance_rule = AttendanceTimeRule.objects.filter(school=school).first()
        now = timezone.localtime()
        current_time = now.time()

        with transaction.atomic():
            today = timezone.localdate()
            rule_start_time = attendance_rule.start_time if attendance_rule else None
            attendance, created = Attendance.objects.select_for_update().get_or_create(
                staff=staff,
                attendance_date=today,
                defaults={
                    "school": school,
                    "category": staff.category,
                    "name": staff.name,
                    "is_present": True,
                    "date_time": now,
                    "check_in": now,
                    "is_half_day": is_after_time(current_time, rule_start_time),
                },
            )

            if not created:
                if attendance.check_out:
                    raise serializers.ValidationError(
                        "Check-out has already been recorded for today."
                    )

                attendance.check_out = now
                update_fields = ["check_out"]

                rule_end_time = attendance_rule.end_time if attendance_rule else None
                if is_before_time(current_time, rule_end_time):
                    attendance.is_half_day = True
                    update_fields.append("is_half_day")

                attendance.save(update_fields=update_fields)
                return attendance

            return attendance


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


class AnnouncementTargetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnnouncementTarget
        fields = "__all__"
        read_only_fields = ["school", "announcement"]


class AnnouncementSerializer(serializers.ModelSerializer):
    targets = AnnouncementTargetSerializer(many=True, required=False)

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "description",
            "publish_at",
            "expires_at",
            "targets",
            "school",
        ]
        read_only_fields = ["school"]

    def create(self, validated_data):
        targets_data = validated_data.pop("targets", [])
        user = self.context["request"].user

        print(targets_data)

        announcement = Announcement.objects.create(school=user.school, **validated_data)

        for target_data in targets_data:
            AnnouncementTarget.objects.create(
                school=user.school, announcement=announcement, **target_data
            )

        return announcement


class GetAnnouncementSerializer(serializers.ModelSerializer):
    targets = AnnouncementTargetSerializer(many=True, read_only=True)

    class Meta:
        model = Announcement
        fields = ["id", "title", "description", "publish_at", "expires_at", "targets"]


# =================FEE MANAGEMENT SERIALIZERS====================


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

class AcademicYearSerializer(serializers.ModelSerializer):
    start_year = serializers.IntegerField(write_only=True, required=False)
    end_year = serializers.IntegerField(write_only=True, required=False)

    month_numbers = serializers.SerializerMethodField()
    billing_periods = serializers.SerializerMethodField()

    class Meta:
        model = AcademicYear
        fields = [
            "id",
            "school",
            "name",
            "start_month",
            "end_month",
            "start_year",
            "end_year",
            "month_numbers",
            "billing_periods",
        ]
        read_only_fields = ["school", "name"]

    def get_month_numbers(self, obj):
        return obj.get_month_numbers()

    def get_billing_periods(self, obj):
        return obj.get_billing_periods()

    def validate(self, attrs):
        start_month = attrs.get(
            "start_month", getattr(self.instance, "start_month", None)
        )
        end_month = attrs.get(
            "end_month", getattr(self.instance, "end_month", None)
        )

        if not self.instance and (start_month is None or end_month is None):
            raise serializers.ValidationError(
                {
                    "start_month": "Start month is required.",
                    "end_month": "End month is required.",
                }
            )

        for field_name, month in [
            ("start_month", start_month),
            ("end_month", end_month),
        ]:
            if month is not None and (month < 1 or month > 12):
                raise serializers.ValidationError(
                    {field_name: "Month must be between 1 and 12."}
                )

        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None

        start_year = attrs.get("start_year")
        end_year = attrs.get("end_year")

        if start_year is not None or end_year is not None:

            if start_year is None or end_year is None:
                raise serializers.ValidationError(
                    {
                        "start_year": "Both start_year and end_year are required.",
                        "end_year": "Both start_year and end_year are required.",
                    }
                )

            if len(str(start_year)) != 4 or len(str(end_year)) != 4:
                raise serializers.ValidationError(
                    "Year values must be 4 digits."
                )

            if end_year != start_year + 1:
                raise serializers.ValidationError(
                    "End year must be start_year + 1."
                )

            attrs["name"] = f"{start_year}-{str(end_year)[-2:]}"

        name = attrs.get("name", getattr(self.instance, "name", None))

        if school and name:
            queryset = AcademicYear.objects.filter(school=school, name=name)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {"name": "This academic year already exists for this school."}
                )

        if school and start_month is not None and end_month is not None:
            queryset = AcademicYear.objects.filter(
                school=school,
                start_month=start_month,
                end_month=end_month,
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {
                        "start_month": "An academic year with the same start and end month already exists for this school.",
                        "end_month": "An academic year with the same start and end month already exists for this school.",
                    }
                )

        return attrs

    def create(self, validated_data):
        validated_data.pop("start_year", None)
        validated_data.pop("end_year", None)

        return AcademicYear.objects.create(**validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("start_year", None)
        validated_data.pop("end_year", None)

        return super().update(instance, validated_data)


class FeeWiseClassSerializer(serializers.ModelSerializer):
    feetype_name = serializers.CharField(source="feetype.name", read_only=True)
    school_class_name = serializers.CharField(
        source="school_class.get_school_class_display", read_only=True
    )

    class Meta:
        model = FeeWiseClass
        fields = [
            "id",
            "school",
            "feetype",
            "feetype_name",
            "school_class",
            "school_class_name",
            "amount",
            "late_fee_enabled",
            "grace_days",
            "late_fee_type",
            "late_fee_amount",
            "max_late_fee",
        ]
        read_only_fields = ["school", "feetype_name", "school_class_name"]

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
            return obj.student.school_class.get_school_class_display()
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
    feetype = serializers.PrimaryKeyRelatedField(read_only=True)
    feetype_name = serializers.CharField(source="feetype.name", read_only=True)
    balance_after_payment = serializers.SerializerMethodField()

    class Meta:
        model = StudentFeePayment
        fields = [
            "id",
            "school",
            "student_fee",
            "student",
            "student_name",
            "feetype",
            "feetype_name",
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
            "is_verified",
            "verified_by",
            "verified_at",
            "balance_after_payment",
            "created_at",
        ]
        read_only_fields = [
            "school",
            "student",
            "student_name",
            "feetype",
            "feetype_name",
            "razorpay_order_id",
            "razorpay_payment_id",
            "razorpay_signature",
            "collected_by",
            "verified_by",
            "verified_at",
            "balance_after_payment",
            "created_at",
        ]

    def get_student_name(self, obj):
        return " ".join(
            filter(
                None, [obj.student.surname, obj.student.name, obj.student.father_name]
            )
        )

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

        paid_except_this = student_fee.payments.filter(is_verified=True).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")
        if self.instance:
            if self.instance.is_verified:
                paid_except_this -= self.instance.amount

        remaining_amount = student_fee.payable_amount - paid_except_this
        if amount > remaining_amount:
            raise serializers.ValidationError(
                {
                    "amount": f"Amount cannot be greater than remaining balance {remaining_amount}."
                }
            )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        if not validated_data.get("payment_date"):
            validated_data["payment_date"] = timezone.now()
        if user:
            validated_data["collected_by"] = user
        if validated_data.get("is_verified") and user:
            validated_data["verified_by"] = user
            validated_data["verified_at"] = timezone.now()

        payment = super().create(validated_data)
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


# ===================================================


# class SchoolSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = School
#         fields = "__all__"


# class WorkingDaySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = WorkingDay
#         fields = "__all__"

# class HolidaySerializer(serializers.ModelSerializer):
#     class Meta:
#         model = Holiday
#         fields = "__all__"


class ClassDivSerializer(serializers.ModelSerializer):
    class Meta:
        model = Division
        fields = "__all__"

    # class SubjectSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = Subject
    #         fields = "__all__"

    # class TeacherStaffSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = Staff
    #         fields = "__all__"

    # class LectureSlotSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = LectureSlot
    #         fields = "__all__"

    # class BreakSlotSerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = BreakSlot
    #         fields = "__all__"

    # class TimetableEntrySerializer(serializers.ModelSerializer):
    #     class Meta:
    #         model = TimetableEntry
    #         fields = "__all__"

    #     def validate(self, attrs):
    #         request = self.context.get("request")
    #         school = getattr(getattr(request, "user", None), "school", None)

    #         timetable = attrs.get("timetable", getattr(self.instance, "timetable", None))
    #         lecture_slot = attrs.get(
    #             "lecture_slot", getattr(self.instance, "lecture_slot", None)
    #         )
    #         subject = attrs.get("subject", getattr(self.instance, "subject", None))
    #         teacher_staff = attrs.get(
    #             "teacher_staff", getattr(self.instance, "teacher_staff", None)
    #         )

    #         if not timetable or not lecture_slot or not subject or not teacher_staff:
    #             return attrs

    #         if school and timetable.school_id != school.id:
    #             raise serializers.ValidationError(
    #                 {"timetable": "Invalid timetable for this school."}
    #             )

    #         if school and lecture_slot.school_id != school.id:
    #             raise serializers.ValidationError(
    #                 {"lecture_slot": "Invalid lecture slot for this school."}
    #             )

    #         if lecture_slot.timetable_id != timetable.id:
    #             raise serializers.ValidationError(
    #                 {"lecture_slot": "Lecture slot does not belong to this timetable."}
    #             )

    #         assigned_teacher = AssignClass.objects.filter(
    #             school=school,
    #             division=timetable.class_div,
    #             subject=subject,
    #             teacher=teacher_staff,
    #         )

    #         if not assigned_teacher.exists():
    #             raise serializers.ValidationError(
    #                 {
    #                     "teacher_staff": (
    #                         "This teacher is not assigned to this subject and division."
    #                     )
    #                 }
    #             )

    #         if lecture_slot.lecture_number == 1 and not assigned_teacher.filter(
    #             is_class_teacher=True
    #         ).exists():
    #             raise serializers.ValidationError(
    #                 {"teacher_staff": "First lecture must be assigned to class teacher."}
    #             )

    #         return attrs

    # class TimetableSerializer(serializers.ModelSerializer):

    #     lecture_slots = LectureSlotSerializer(many=True, required=False)
    #     break_slots = BreakSlotSerializer(many=True, required=False)
    #     working_days = serializers.ListField(
    #         child=serializers.ChoiceField(choices=WorkingDay.DAY_CHOICES),
    #         write_only=True,
    #         required=False,
    #     )

    #     class Meta:
    #         model = Timetable
    #         fields = "__all__"

    #     def create(self, validated_data):

    #         request = self.context["request"]
    #         school = request.user.school

    #         lectures = validated_data.pop("lecture_slots", [])
    #         breaks = validated_data.pop("break_slots", [])
    #         working_days = validated_data.pop("working_days", [])
    #         validated_data.pop("school", None)

    #         for day in working_days:
    #             WorkingDay.objects.get_or_create(school=school, day=day)

    #         timetable = Timetable.objects.create(
    #             school=school,
    #             **validated_data
    #         )

    #         for l in lectures:
    #             LectureSlot.objects.create(
    #                 school=school,
    #                 timetable=timetable,
    #                 **l
    #             )

    #         for b in breaks:
    #             BreakSlot.objects.create(
    #                 school=school,
    #                 timetable=timetable,
    #                 **b
    #             )

    #         return timetable

    def update(self, instance, validated_data):

        lectures = validated_data.pop("lecture_slots", None)
        breaks = validated_data.pop("break_slots", None)
        working_days = validated_data.pop("working_days", None)
        validated_data.pop("school", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        school = instance.school

        if working_days is not None:
            for day in working_days:
                WorkingDay.objects.get_or_create(school=school, day=day)

        if lectures is not None:
            instance.lecture_slots.all().delete()
            for l in lectures:
                LectureSlot.objects.create(school=school, timetable=instance, **l)

        if breaks is not None:
            instance.break_slots.all().delete()
            for b in breaks:
                BreakSlot.objects.create(school=school, timetable=instance, **b)

        return instance


class SlotSerializer(serializers.ModelSerializer):

    class Meta:
        model = Slot
        exclude = ["timetable", "school"]

    def validate(self, attrs):

        is_lecture = attrs.get("is_lecture")
        is_break = attrs.get("is_break")

        subject = attrs.get("subject")
        teacher = attrs.get("teacher")

        slot_start_time = attrs.get("slot_start_time")
        slot_end_time = attrs.get("slot_end_time")

        # both true or both false
        if is_lecture == is_break:
            raise serializers.ValidationError("Slot must be either lecture or break")

        # time validation
        if slot_start_time >= slot_end_time:
            raise serializers.ValidationError(
                "End time must be greater than start time"
            )

        # lecture validation
        if is_lecture:

            if not subject:
                raise serializers.ValidationError("Lecture slot requires subject")

            if not teacher:
                raise serializers.ValidationError("Lecture slot requires teacher")

        # break validation
        if is_break:

            if subject or teacher:
                raise serializers.ValidationError(
                    "Break slot cannot have subject or teacher"
                )

        return attrs


class TimeTableSerializer(serializers.ModelSerializer):

    # slots = SlotSerializer(many=True)
    slots = SlotSerializer(many=True)

    class Meta:
        model = Time_Table_tb
        fields = "__all__"
        read_only_fields = ["school"]

    # def validate(self, attrs):

    #     start_time = attrs.get("start_time")
    #     end_time = attrs.get("end_time")

    #     if start_time >= end_time:
    #         raise serializers.ValidationError(
    #             "End time must be greater than start time"
    #         )

    #     return
    def validate(self, attrs):

        start_time = attrs.get("start_time") or getattr(
            self.instance, "start_time", None
        )
        end_time = attrs.get("end_time") or getattr(self.instance, "end_time", None)
        slots = self.initial_data.get("slots", [])

        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError(
                "End time must be greater than start time"
            )

        lecture_count = 0
        previous_end = None

        for slot in slots:

            slot_start = slot.get("slot_start_time")
            slot_end = slot.get("slot_end_time")

            if previous_end and previous_end != slot_start:
                raise serializers.ValidationError("Slot timings are not continuous")

            previous_end = slot_end

            if slot.get("is_lecture"):
                lecture_count += 1

        if lecture_count != attrs.get("total_lecture"):
            raise serializers.ValidationError("Total lecture count mismatch")

        request = self.context.get("request")
        school = getattr(getattr(request, "user", None), "school", None)
        class_division = attrs.get("class_division") or getattr(
            self.instance, "class_division", None
        )
        day = attrs.get("day") or getattr(self.instance, "day", None)

        if school and class_division and class_division.school_id != school.id:
            raise serializers.ValidationError(
                {"class_division": "Invalid division for this school."}
            )

        if school and class_division and day:
            existing = Time_Table_tb.objects.filter(
                school=school,
                class_division=class_division,
                day=day,
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            conflicting_timetable = existing.first()
            if conflicting_timetable:
                raise serializers.ValidationError(
                    {
                        "day": (
                            "A timetable for this class division and day "
                            "already exists."
                        ),
                        "existing_timetable_id": conflicting_timetable.id,
                    }
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):

        slots_data = validated_data.pop("slots")

        timetable = Time_Table_tb.objects.create(**validated_data)

        for slot_data in slots_data:

            teacher = slot_data.get("teacher")

            # CHECK CLASS TEACHER LOGIC
            if teacher and slot_data.get("slot_number") == 1:

                is_class_teacher = AssignClass.objects.filter(
                    school=timetable.school,
                    division=timetable.class_division,
                    teacher=teacher,
                    is_class_teacher=True,
                ).exists()

                if not is_class_teacher:
                    raise serializers.ValidationError(
                        {"slot_1": ("First slot teacher must " "be class teacher")}
                    )

            Slot.objects.create(
                timetable=timetable, school=timetable.school, **slot_data
            )

        return timetable

    @transaction.atomic
    def update(self, instance, validated_data):

        slots_data = validated_data.pop("slots", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        if slots_data is not None:

            instance.slots.all().delete()

            for slot_data in slots_data:

                teacher = slot_data.get("teacher")

                if teacher and slot_data.get("slot_number") == 1:

                    is_class_teacher = AssignClass.objects.filter(
                        school=instance.school,
                        division=instance.class_division,
                        teacher=teacher,
                        is_class_teacher=True,
                    ).exists()

                    if not is_class_teacher:
                        raise serializers.ValidationError(
                            {"slot_1": ("First slot teacher " "must be class teacher")}
                        )

                Slot.objects.create(
                    timetable=instance, school=instance.school, **slot_data
                )

        return instance


# -------------------------
# Student attendance


class StudentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Student
        fields = ["id", "surname", "name", "gr_no"]


# serializers.py

from rest_framework import serializers
from .models import StudentAttendance


class StudentAttendanceSerializer(serializers.ModelSerializer):

    class Meta:
        model = StudentAttendance
        fields = [
            "id",
            "student",
            "is_present",
            "is_absent",
            "attendance_date",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "school",
            "attendance_by",
            "attendance_date",
            "created_at",
        ]

    def validate(self, attrs):

        is_present = attrs.get("is_present", False)
        is_absent = attrs.get("is_absent", False)

        if is_present and is_absent:
            raise serializers.ValidationError(
                "Student cannot be both present and absent."
            )

        if not is_present and not is_absent:
            raise serializers.ValidationError(
                "Either present or absent must be selected."
            )

        return attrs

    def create(self, validated_data):

        request = self.context["request"]

        validated_data["school"] = request.user.school
        validated_data["attendance_by"] = request.user.staff

        attendance = super().create(validated_data)

        StudentNotification.objects.create(
            school=attendance.school,
            student=attendance.student,
            created_by=request.user.staff,
            notification_type="ATTENDANCE",
            title="Attendance Updated",
            message=(
                f"{attendance.student.name} marked "
                f"{'Present' if attendance.is_present else 'Absent'} "
                f"on {attendance.attendance_date}"
            )
        )

        return attendance


from rest_framework import serializers
from .models import Homework, HomeworkSubmission

# ======================== HOMEWORK SERIALIZERS ========================


class HomeworkSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and listing homework.
    Teachers create homework for a division.
    """

    division_name = serializers.CharField(source="division.division", read_only=True)
    school_class_name = serializers.CharField(
        source="division.SchoolClass.get_school_class_display", read_only=True
    )
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)
    submission_count = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields = [
            "id",
            "school",
            "division",
            "division_name",
            "school_class_name",
            "teacher",
            "teacher_name",
            "title",
            "description",
            "assigned_date",
            "due_date",
            "attachment",
            "is_active",
            "submission_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "school",
            "teacher",
            "teacher_name",
            "division_name",
            "school_class_name",
            "submission_count",
            "assigned_date",
            "created_at",
            "updated_at",
        ]

    def get_submission_count(self, obj):
        """Return count of total submissions for this homework"""
        return obj.submissions.count()

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        division = attrs.get("division", getattr(self.instance, "division", None))

        if not division:
            raise serializers.ValidationError({"division": "Division is required."})

        if school and division.school_id != school.id:
            raise serializers.ValidationError(
                {"division": "Invalid division for this school."}
            )

        return attrs
    
    def validate_due_date(self, value):
        if value < date.today():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        # Automatically set school and teacher from request
        validated_data["school"] = user.school
        validated_data["teacher"] = user.staff if hasattr(user, "staff") else None

        return super().create(validated_data)


class GetHomeworkSerializer(serializers.ModelSerializer):
    """
    Serializer for students to view homework for their division.
    Shows homework details and submission status for the logged-in student.
    """

    division_name = serializers.CharField(source="division.division", read_only=True)
    school_class_name = serializers.CharField(
        source="division.SchoolClass.get_school_class_display", read_only=True
    )
    teacher_name = serializers.CharField(source="teacher.name", read_only=True)

    # Student's submission for this homework
    student_submission = serializers.SerializerMethodField()
    is_submitted = serializers.SerializerMethodField()
    submission_status = serializers.SerializerMethodField()
    is_late = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields = [
            "id",
            "division",
            "division_name",
            "school_class_name",
            "teacher_name",
            "title",
            "description",
            "assigned_date",
            "due_date",
            "attachment",
            "is_active",
            "is_submitted",
            "submission_status",
            "student_submission",
            "is_late",
        ]
        read_only_fields = fields

    def get_student_submission(self, obj):
        """Get the logged-in student's submission for this homework"""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "student"):
            return None

        submission = obj.submissions.filter(student__user=request.user).first()

        if submission:
            return HomeworkSubmissionDetailSerializer(submission).data
        return None

    def get_is_submitted(self, obj):
        """Check if the logged-in student has submitted this homework"""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "student"):
            return False

        return obj.submissions.filter(student__user=request.user).exists()

    def get_submission_status(self, obj):
        """Get the logged-in student's submission status"""
        request = self.context.get("request")
        if not request or not hasattr(request.user, "student"):
            return None

        submission = obj.submissions.filter(student__user=request.user).first()

        return submission.status if submission else None

    def get_is_late(self, obj):
        """Check if due date has passed"""
        from django.utils import timezone

        return timezone.now().date() > obj.due_date


class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for students to submit homework and teachers to check submissions.
    """

    student_name = serializers.SerializerMethodField()
    homework_title = serializers.CharField(source="homework.title", read_only=True)
    submission_date = serializers.SerializerMethodField()

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id",
            "school",
            "homework",
            "homework_title",
            "student",
            "student_name",
            "attachment",
            "submitted_at",
            "submission_date",
            "status",
            "marks",
            "teacher_remark",
            "checked_by",
            "checked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "school",
            "student",
            "student_name",
            "homework_title",
            "submitted_at",
            "submission_date",
            "checked_by",
            "checked_at",
            "created_at",
            "updated_at",
        ]

    def get_student_name(self, obj):
        """Return formatted student name"""
        return " ".join(
            filter(
                None,
                [
                    obj.student.surname,
                    obj.student.name,
                    obj.student.father_name,
                ],
            )
        )

    def get_submission_date(self, obj):
        """Format submission date"""
        return obj.submitted_at.date() if obj.submitted_at else None

    def validate(self, attrs):
        request = self.context.get("request")
        school = getattr(request.user, "school", None) if request else None
        homework = attrs.get("homework", getattr(self.instance, "homework", None))
        student = attrs.get("student", getattr(self.instance, "student", None))

        if not homework:
            raise serializers.ValidationError({"homework": "Homework is required."})

        if not student:
            raise serializers.ValidationError({"student": "Student is required."})

        if school and homework.school_id != school.id:
            raise serializers.ValidationError(
                {"homework": "Invalid homework for this school."}
            )

        if school and student.school_id != school.id:
            raise serializers.ValidationError(
                {"student": "Invalid student for this school."}
            )

        # Check if student belongs to the class/division this homework is for
        # homework_division = (homework.division.division or "").strip().lower()
        # student_division = (student.division or "").strip()

        # if "(" in student_division and ")" in student_division:
        #     student_division = (
        #         student_division.rsplit("(", 1)[-1].split(")", 1)[0].strip()
        #     )

        # student_division = student_division.lower()
        
        homework_division = (homework.division.division or "").strip().lower()
        student_division = (student.division.division or "").strip().lower()

        if (
            homework.division_id != student.division_id
            or homework.division.SchoolClass_id != student.school_class_id
        ):
            raise serializers.ValidationError(
                {
                    "student": "This student is not in the class/division assigned for this homework."
                }
            )

        if (
            homework.division.SchoolClass_id != student.school_class_id
            or homework_division != student_division
        ):
            raise serializers.ValidationError(
                {
                    "student": "This student is not in the class/division assigned for this homework."
                }
            )

        # Check for duplicate submission (on create only)
        if not self.instance:
            if HomeworkSubmission.objects.filter(
                homework=homework, student=student
            ).exists():
                raise serializers.ValidationError(
                    "This student has already submitted this homework."
                )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        validated_data["school"] = user.school
        validated_data["submitted_at"] = timezone.now()

        return super().create(validated_data)


class HomeworkSubmissionDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for viewing a single submission with all details.
    """

    student_name = serializers.SerializerMethodField()
    homework_title = serializers.CharField(source="homework.title", read_only=True)
    teacher_name = serializers.CharField(source="checked_by.staff.name", read_only=True)

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id",
            "homework",
            "homework_title",
            "student",
            "student_name",
            "attachment",
            "submitted_at",
            "status",
            "marks",
            "teacher_remark",
            "checked_by",
            "teacher_name",
            "checked_at",
        ]
        read_only_fields = fields

    def get_student_name(self, obj):
        return " ".join(
            filter(
                None,
                [
                    obj.student.surname,
                    obj.student.name,
                    obj.student.father_name,
                ],
            )
        )


class CheckHomeworkSubmissionSerializer(serializers.ModelSerializer):
    """
    Serializer for teachers to check and grade homework submissions.
    """

    student_name = serializers.CharField(source="student.name", read_only=True)

    class Meta:
        model = HomeworkSubmission
        fields = [
            "id",
            "student_name",
            "status",
            "marks",
            "teacher_remark",
            "checked_at",
        ]
        read_only_fields = [
            "id",
            "student_name",
            "checked_at",
        ]

    def validate_marks(self, value):
        """Validate marks are between 0 and 100"""
        if value is not None:
            if value < 0 or value > 100:
                raise serializers.ValidationError("Marks must be between 0 and 100.")
        return value

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", None))

        if status == "checked" and not attrs.get("marks"):
            raise serializers.ValidationError(
                {"marks": "Marks are required when status is marked as 'checked'."}
            )

        return attrs

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None

        if validated_data.get("status") == "checked" and not instance.checked_by:
            validated_data["checked_by"] = user
            validated_data["checked_at"] = timezone.now()

        return super().update(instance, validated_data)


class StudentHomeworkListSerializer(serializers.ModelSerializer):
    """
    Serializer for students to view all homework for their division.
    Shows division-wise homework with submission status.
    """

    class Meta:
        model = Homework
        fields = [
            "id",
            "title",
            "description",
            "assigned_date",
            "due_date",
            "attachment",
            "is_active",
        ]
        read_only_fields = fields


# --------------------------------GET STUDENT DATA----------------------------


class StudentGetSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source = "school_class.school_class",read_only = True)
    class Meta:
        model = Student
        fields = ["id","surname", "name", "father_name", "mother_name", "school_class","class_name"]

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

        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades +
            "haarcascade_frontalface_default.xml"
        )

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5
        )

        if len(faces) == 0:
            raise serializers.ValidationError(
                "No face detected."
            )

        if len(faces) > 1:
            raise serializers.ValidationError(
                "Multiple faces detected."
            )

        image.seek(0)

        return image
    
    def create(self, validated_data):
            request = self.context["request"]
            staff = Staff.objects.get(user=request.user)

            face, created = StaffFace.objects.get_or_create(
                staff=staff,
                defaults=validated_data
            )

            if not created:
                face.face_image = validated_data["face_image"]
                
            face.is_enrolled = True 
            face.save()

            return face

class ParentCreateSerializer(serializers.Serializer):
    username = serializers.CharField()
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def create(self, validated_data):

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )

        parent = Parent.objects.create(
            user=user
        )

        return parent

class StaffFaceVerifySerializer(serializers.Serializer):
    image=serializers.ImageField()
    
class StudentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model=StudentDocument
        fields=["student","document_type","title","description","document"]

class StudentNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=StudentNotification
        fields=["notification_type","title","message"]

class ExamSerializer(serializers.ModelSerializer):
    class Meta:
        model=Exam
        fields=["title","description","exam_date","start_time","end_time","class_group"]

class ExamNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=ExamNotification
        fields=["exam","title","message"]

class HomeworkSubmissionSerializer(serializers.ModelSerializer):
    class Meta():
        model=HomeworkSubmission
        fields=["student","homework","file","submitted_at"]
        read_only_fields=["submitted_at"]

    def validate(self, attrs):
        homework = attrs.get("homework")

        if homework and homework.due_date:
            submission_date = now().date() 
            due_date = homework.due_date

            if submission_date > due_date:
                raise serializers.ValidationError(
                    "You cannot submit homework after the due date."
                )

        return attrs