import random
from rest_framework import serializers
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from .models import *
from .academic_serializers import ALLOWED_STUDENT_FIELD_MAPPINGS

User = get_user_model()


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


class AdmissionFieldValueReadSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source="field.label", read_only=True)

    class Meta:
        model = AdmissionFieldValue
        fields = ["id", "field", "field_label", "value"]


# 2


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


class DocumentFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentField
        fields = ["id", "label", "is_required", "order"]


# ===================== MAIN SERIALIZER =====================
# 4


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






class AdmissionFeeStructureSerializer(serializers.ModelSerializer):
    class_name = serializers.PrimaryKeyRelatedField(queryset=SchoolClass.objects.all())
    class_label = serializers.CharField(source="class_name.school_class", read_only=True)
    class_code = serializers.CharField(source="class_name.school_class", read_only=True)

    class Meta:
        model = AdmissionFeeStructure
        fields = ["class_name", "class_label", "class_code", "fee_amount"]






class AdmissionFeeSerializer(serializers.ModelSerializer):

    class Meta:
        model = AdmissionFee
        fields = [
            "amount",
            "currency",
            "payment_mode",
            "paid_at",
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
    school_name = serializers.CharField(source="school.name", read_only=True)
    fee_structures = AdmissionFeeStructureSerializer(many=True, read_only=True)
    document_fields = DocumentFieldSerializer(many=True, read_only=True)

    class Meta:
        model = AdmissionForm
        fields = [
            "id",
            "title",
            "school",
            "school_name",
            "school_slug",
            "description",
            "is_active",
            "unique_link",
            "academic_year",
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

    school = serializers.PrimaryKeyRelatedField(
        read_only=True,
    )

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
            "school",
            "fee_type",
            "fee_amount",
            "payment_status",
        ]

    def validate(self, data):
        form = data["form"]
        field_values = data["field_values"]
        school_class = data.get("school_class")
        admission_number = data.get("admission_number")

        request = self.context.get("request")
        user = getattr(request, "user", None)
        school = getattr(user, "school", None) or getattr(form, "school", None)
        data["school"] = school

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

            school_class = None
            if str(raw_value).isdigit():
                school_class = SchoolClass.objects.filter(
                    id=int(raw_value),
                    school=form.school,
                ).first()
            else:
                school_class = SchoolClass.objects.filter(
                    school_class=raw_value,
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

        if str(field_value.value).isdigit():
            return SchoolClass.objects.filter(
                id=int(field_value.value),
                school=instance.school,
            ).first()

        return SchoolClass.objects.filter(
            school_class=field_value.value,
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
# pyrefly: ignore [missing-import]
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

        # Safely update or create field values without wiping out existing ones
        if field_values_data is not None:
            for item in field_values_data:
                field_obj = item.get("field")
                val = item.get("value")
                if field_obj:
                    AdmissionFieldValue.objects.update_or_create(
                        admission=instance,
                        field=field_obj,
                        defaults={"value": val},
                    )
                    if field_obj.label and any(k in field_obj.label.lower() for k in ["division", "section", "sec"]):
                        Student.objects.filter(admission=instance).update(division=val)

        # Handle direct division update in request data
        req = self.context.get("request")
        if req and hasattr(req, "data"):
            div_val = req.data.get("division")
            if div_val:
                Student.objects.filter(admission=instance).update(division=div_val)

        instance.save()
        return instance


# ===========================================================================

#  =========UPDATE DOCUMENT BY CLERK AFTER SUBMISSION=========




class AdmissionDocumentSerializer(serializers.ModelSerializer):
    documents = AdmissionDocumentItemSerializer(
        source="admission_documents", many=True  # related_name
    )

    class Meta:
        model = Admission
        fields = ["admission_number", "documents"]
        read_only_fields = ["admission_number"]


# pyrefly: ignore [missing-import]
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




class AdmissionSectionWiseReadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    order = serializers.IntegerField()
    field_values = AdmissionFieldValueReadSerializer(many=True)




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
        request = self.context.get("request")
        school = request.user.school

        if User.objects.filter(username=gr_no, school=school).exists():
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
                student_user = User.objects.create(username=gr_no)
                student_user.set_password(gr_no)

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


# class PrincipleVerifySerializr(serializers.ModelSerializer):
#     field_values = StudentFieldValueReadSerializer(many=True, read_only=True)

#     class Meta:
#         model = Student
#         fields = ["principle_verified", "principle_verified_at", "field_values"]


# =======set subject serializers========




class GetAdmissionDataSerializer(serializers.ModelSerializer):
    field_values = AdmissionFieldValueReadSerializer(many=True, read_only=True)
    documents = AdmissionDocumentReadSerializer(many=True, read_only=True)
    gr_no = serializers.SerializerMethodField()
    division = serializers.SerializerMethodField()

    def get_gr_no(self, obj):
        sv = StudentVerify.objects.filter(admission_number=obj.admission_number).first()
        if sv and sv.gr_no:
            return sv.gr_no
        if hasattr(obj, "student") and obj.student and obj.student.gr_no:
            return obj.student.gr_no
        return getattr(obj, "gr_no", None)

    def get_division(self, obj):
        st = Student.objects.filter(admission=obj).first()
        if st and st.division:
            return st.division.division if hasattr(st.division, "division") else str(st.division)
        for fv in obj.field_values.all():
            if fv.field and any(k in fv.field.label.lower() for k in ["division", "section", "sec"]):
                return fv.value
        return None

    class Meta:
        model = Admission
        fields = [
            "id",
            "admission_number",
            "status",
            "gr_no",
            "division",
            "field_values",
            "documents",
        ]




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
    class_name = serializers.CharField(source = "school_class.school_class", default="", read_only=True)
    email = serializers.SerializerMethodField()

    def get_email(self, obj):
        if obj.user and obj.user.email:
            return obj.user.email
        if hasattr(obj, "admission") and obj.admission:
            fv = obj.admission.field_values.filter(
                field__label__icontains="email"
            ).first()
            if fv and fv.value:
                return fv.value
        return None
    
    class Meta:
        model = Student
        fields = [
            "id",
            "user",
            "name",
            "surname",
            "email",
            "mobile",
            "school",
            "school_class",
            "class_name",
            "division",
            "is_active",
            "created_at",
            "gr_no",
            "studentverify",
            "extradata"
        ]

        read_only_fields = fields




class StudentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Student
        fields = ["id", "surname", "name", "gr_no"]


# serializers.py
    
# pyrefly: ignore [missing-import]
from rest_framework import serializers
from .models import StudentAttendance




class StudentGetSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source = "school_class.school_class",read_only = True)
    class Meta:
        model = Student
        fields = ["id", "gr_no", "surname", "name", "father_name", "mother_name", "school_class", "class_name"]



class StudentDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model=StudentDocument
        fields=["id","student","document_type","title","description","document"]



class StudentNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model=StudentNotification
        fields=["notification_type","title","message"]




