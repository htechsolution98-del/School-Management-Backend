from django.forms.models import model_to_dict
from django.db import transaction
from rest_framework import serializers
from .models import Student, StudentExtraData, SchoolProfileField, StudentProfileValue
from .student_serializers import StudentGetSerializer
from .student_profile_services import completion, documents_data, file_url, profile_sections, document_records, validate_aadhaar, validate_udise, validate_abc_id, is_aadhaar_field


class StudentProfileSerializer(StudentGetSerializer):
    completion = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()
    extra_details = serializers.SerializerMethodField()
    guardians = serializers.SerializerMethodField()
    admission_number = serializers.CharField(source="admission.admission_number", read_only=True, default=None)
    document_slots = serializers.SerializerMethodField()
    custom_ids = serializers.SerializerMethodField()
    shared_document_fields = serializers.SerializerMethodField()
    custom_id_values = serializers.DictField(child=serializers.CharField(max_length=255, allow_blank=True), required=False, write_only=True)

    class Meta(StudentGetSerializer.Meta):
        fields = StudentGetSerializer.Meta.fields + ["completion", "sections", "extra_details", "guardians", "admission_number", "document_slots", "custom_ids", "shared_document_fields", "custom_id_values"]

    def validate_aadhar_number(self, value):
        return validate_aadhaar(value)

    def validate_udise_no(self, value):
        return validate_udise(value)

    def validate_abc_id(self, value):
        return validate_abc_id(value)

    def validate(self, attrs):
        request = self.context.get("request")
        school_id = self.instance.school_id if self.instance else getattr(request.user, "school_id", None)
        for key in ("school_class", "academic_year"):
            item = attrs.get(key)
            if item and item.school_id != school_id:
                raise serializers.ValidationError({key: "This record belongs to another school."})
        return attrs

    def validate_custom_id_values(self, values):
        school_id = self.instance.school_id if self.instance else getattr(self.context["request"].user, "school_id", None)
        fields = set(SchoolProfileField.objects.filter(school_id=school_id, kind="ID").values_list("id", flat=True))
        if any(not key.isdigit() or int(key) not in fields for key in values):
            raise serializers.ValidationError("Choose ID fields belonging to this school.")
        return values

    def get_custom_ids(self, obj):
        values = {value.field_id: value.value for value in obj.profile_values.all()}
        return [{"id": field.id, "label": field.label, "value": values.get(field.id, "")} for field in obj.school.profile_fields.all() if field.kind == "ID"]

    def get_shared_document_fields(self, obj):
        return [{"id": field.id, "label": field.label} for field in obj.school.profile_fields.all() if field.kind == "DOCUMENT"]

    def get_class_name(self, obj):
        if obj.school_class_id:
            return obj.school_class.school_class
        if obj.admission_id:
            for item in obj.admission.field_values.all():
                if item.field.map_to_student_field == "school_class":
                    return item.value
        return None

    def get_email(self, obj):
        if obj.user_id and obj.user.email:
            return obj.user.email
        if obj.admission_id and obj.admission.temp_user_id:
            return obj.admission.temp_user.email or None
        return None

    def get_full_name(self, obj):
        father = (obj.father_name or "").strip()
        surname = (obj.surname or "").strip()
        if surname and father.casefold().endswith(" " + surname.casefold()):
            father = father[:-(len(surname) + 1)].strip()
        parts = [part for part in [obj.name, father, surname] if part]
        return " ".join(parts) if parts else super().get_full_name(obj)

    @transaction.atomic
    def update(self, instance, validated_data):
        custom = validated_data.pop("custom_id_values", {})
        updated = super().update(instance, validated_data)
        for field_id, value in custom.items():
            StudentProfileValue.objects.update_or_create(student=updated, field_id=int(field_id), defaults={"value": value})
        for key in ("aadhar_number", "abc_id", "udise_no"):
            if key not in validated_data:
                continue
            updated.field_values.filter(field__map_to_student_field=key).update(value=validated_data[key])
            if updated.admission_id:
                updated.admission.field_values.filter(field__map_to_student_field=key).update(value=validated_data[key])
            if key == "aadhar_number":
                for relation in ([updated.field_values, updated.admission.field_values] if updated.admission_id else [updated.field_values]):
                    for value in relation.select_related("field"):
                        if is_aadhaar_field(value.field):
                            value.value = validated_data[key]
                            value.save(update_fields=["value"])
        # Drop prefetched values after mutation so the response reflects the new IDs.
        updated._prefetched_objects_cache = {}
        return updated

    def get_photo_url(self, obj):
        for source, document, field in document_records(obj):
            label = document.document_field.label if source == "adm" else document.title if source == "std" else document.document_name
            if any(word in (label or "").lower() for word in ("photo", "picture", "avatar")):
                return file_url(getattr(document, field), self.context.get("request"))
        return None

    def get_documents(self, obj):
        return documents_data(obj, self.context.get("request"))

    def get_completion(self, obj):
        return completion(obj)

    def get_sections(self, obj):
        return profile_sections(obj)

    def get_extra_details(self, obj):
        return [model_to_dict(extra, exclude=["id", "student"]) for extra in obj.studentextradata_set.all()]

    def get_guardians(self, obj):
        return [{"id": parent.id, "name": parent.user.get_full_name() or parent.user.username, "email": parent.user.email} for parent in obj.perents_set.all() if parent.school_id == obj.school_id]

    def get_document_slots(self, obj):
        if not obj.admission_id or not obj.admission.form_id:
            return []
        return [{"id": field.id, "label": field.label, "is_required": field.is_required} for field in obj.admission.form.document_fields.all() if field.school_id == obj.school_id]

    def to_representation(self, instance):
        # Reads must never save a student or silently change their class/identity.
        data = serializers.ModelSerializer.to_representation(self, instance)
        if not data["name"] and instance.admission_id:
            name = next((value.value for value in instance.admission.field_values.all() if value.field.map_to_student_field == "name" and value.value), None)
            if name:
                data["name"] = name
                data["full_name"] = " ".join(filter(None, [name, instance.father_name, instance.surname]))
        return data


class StudentDocumentMetadataSerializer(serializers.Serializer):
    is_verified = serializers.BooleanField(required=False)
    title = serializers.CharField(max_length=255, required=False)
    document_type = serializers.ChoiceField(choices=["RESULT", "REPORT_CARD", "CERTIFICATE", "ACHIEVEMENT", "OTHER"], required=False)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        source = self.context.get("source", "std")
        allowed = {"title", "expiry_date"} if source == "rte" else {"title", "document_type", "description"} if source == "std" else set()
        invalid = set(self.initial_data) - allowed - {"profile_field", "is_verified", "file", "expected_file", "document_field", "source"}
        if invalid:
            raise serializers.ValidationError({key: "This field cannot be edited for this document." for key in invalid})
        return attrs
