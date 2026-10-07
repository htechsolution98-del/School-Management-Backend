"""Student profile projection and file lifecycle using the configured Django storage."""
import logging
import re
import uuid
from pathlib import Path

from django.db import transaction
from django.db.models import Prefetch, Q
from django.forms.models import model_to_dict
from rest_framework import serializers

from .models import AdmissionDocument, AdmissionFieldValue, DocumentField, RTEDocument, StudentDocument, StudentExtraData, StudentFieldValue

logger = logging.getLogger(__name__)
AADHAAR_ERROR = "Aadhaar number must be exactly 12 digits."
UDISE_ERROR = "UDISE number must be exactly 11 digits."
ABC_ID_ERROR = "ABC ID must be exactly 12 digits."


def validate_aadhaar(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{12}", value.strip()):
        raise serializers.ValidationError(AADHAAR_ERROR)
    return value.strip()


def validate_udise(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{11}", value.strip()):
        raise serializers.ValidationError(UDISE_ERROR)
    return value.strip()


def validate_abc_id(value):
    if value in (None, ""):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{12}", value.strip()):
        raise serializers.ValidationError(ABC_ID_ERROR)
    return value.strip()


def is_aadhaar_field(field):
    return field.map_to_student_field == "aadhar_number" or bool(re.search(r"aadh?aar|aadhar", field.label or "", re.I))


def validate_dynamic_id(attrs):
    field = attrs.get("field")
    if field and is_aadhaar_field(field) and "value" in attrs:
        attrs["value"] = validate_aadhaar(attrs["value"])
    return attrs


class AadhaarValidationMixin:
    def validate_aadhar_number(self, value):
        return validate_aadhaar(value)


class DynamicIDValidationMixin:
    def validate(self, attrs):
        return validate_dynamic_id(attrs)


def profile_queryset(queryset):
    return queryset.select_related("school_class", "academic_year", "verified_by", "admission__temp_user", "admission__form", "user").prefetch_related(
        Prefetch("admission__documents", queryset=AdmissionDocument.objects.select_related("document_field", "verified_by").order_by("id")),
        "admission__form__document_fields",
        Prefetch("admission__field_values", queryset=AdmissionFieldValue.objects.select_related("field__section").order_by("id")),
        Prefetch("field_values", queryset=StudentFieldValue.objects.select_related("field__section").order_by("id")),
        Prefetch("student_documents", queryset=StudentDocument.objects.select_related("uploaded_by", "verified_by").order_by("id")),
        "school__profile_fields", "profile_values", "rte_documents", "admission__rte_documents", "studentextradata_set", "perents_set__user",
    )


def file_url(file, request=None):
    if not file:
        return None
    url = file.url
    return request.build_absolute_uri(url) if request else url


def document_records(student):
    records = []
    if student.admission_id:
        records.extend(("adm", document, "file") for document in student.admission.documents.all())
    records.extend(("std", document, "document") for document in student.student_documents.all() if document.school_id == student.school_id)
    rte = {document.id: document for document in student.rte_documents.all()}
    if student.admission_id:
        rte.update({document.id: document for document in student.admission.rte_documents.all() if document.student_id in (None, student.id)})
    records.extend(("rte", document, "document_file") for document in rte.values())
    return records


def documents_data(student, request=None):
    documents = []
    for source, document, field in document_records(student):
        file = getattr(document, field)
        title = document.document_field.label if source == "adm" else document.title if source == "std" else document.document_name
        verified = document.is_verified
        documents.append({
            "id": f"{source}_{document.id}", "raw_id": document.id, "source": source,
            "profile_field": document.profile_field_id if source == "std" else None, "title": title, "label": title, "url": file_url(file, request), "file_url": file_url(file, request),
            "file_name": file.name, "type": "ADMISSION_DOCUMENT" if source == "adm" else "STUDENT_DOCUMENT" if source == "std" else "RTE_DOCUMENT",
            "document_type": document.document_type if source == "std" else None,
            "description": document.description if source == "std" else None,
            "uploaded_at": document.uploaded_at, "updated_at": document.updated_at if source == "std" else None,
            "document_field": document.document_field_id if source == "adm" else None,
            "is_required": document.document_field.is_required if source == "adm" else False,
            "expiry_date": document.expiry_date if source == "rte" else None,
            "is_verified": verified, "verification_scope": "document",
            "verified_by_name": (document.verified_by.get_full_name() or document.verified_by.username) if verified and document.verified_by_id else None,
            "verified_at": document.verified_at if verified else None,
            "can_edit_metadata": source in ("std", "rte"),
        })
    return documents


def completion(student):
    required = list(student.admission.form.document_fields.all()) if student.admission_id and student.admission.form_id else []
    uploaded = {document.document_field_id for document in student.admission.documents.all() if document.file} if student.admission_id else set()
    missing = [{"id": field.id, "label": field.label} for field in required if field.is_required and field.id not in uploaded]
    all_documents = document_records(student)
    custom_values = {value.field_id: value.value for value in student.profile_values.all()}
    custom_missing = [field.label for field in student.school.profile_fields.all() if field.kind == "ID" and not custom_values.get(field.id)]
    return {"document_count": sum(bool(getattr(document, field)) for _, document, field in all_documents),
            "required_document_count": sum(field.is_required for field in required), "missing_documents": missing,
            "missing_ids": [name for name, value in [("Aadhaar", student.aadhar_number), ("ABC / APAAR", student.abc_id), ("UDISE / PEN", student.udise_no)] if not value] + custom_missing,
            "document_requirements_known": bool(required)}


def profile_sections(student):
    values = {}
    if student.admission_id:
        for value in student.admission.field_values.all():
            values[value.field_id] = value
    for value in student.field_values.all():
        values[value.field_id] = value
    sections = {}
    for value in values.values():
        field = value.field
        current = student.aadhar_number if is_aadhaar_field(field) else getattr(student, field.map_to_student_field, value.value) if field.map_to_student_field in {"name", "surname", "father_name", "mother_name", "mobile", "date_of_birth", "aadhar_number", "abc_id", "udise_no", "division", "roll_no"} else value.value
        sections.setdefault(field.section.title, []).append({"id": field.id, "label": field.label, "value": current, "sensitive": is_aadhaar_field(field), "mapping": field.map_to_student_field})
    return [{"title": title, "fields": fields} for title, fields in sections.items()]


def validate_upload(file):
    if not file:
        raise serializers.ValidationError({"file": "Select a document to upload."})
    if file.size > 10 * 1024 * 1024:
        raise serializers.ValidationError({"file": "Maximum file size is 10 MB."})
    header = file.read(16)
    file.seek(0)
    extension = Path(file.name).suffix.lower()
    valid = (extension == ".pdf" and header.startswith(b"%PDF-")) or (extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff")) or (extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n")) or (extension == ".webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP")
    if not valid:
        raise serializers.ValidationError({"file": "Upload a valid PDF, JPG, PNG or WebP document."})
    file.name = f"{uuid.uuid4().hex}{extension}"
    return file


def delete_unreferenced_file(storage, name):
    if not name:
        return
    if AdmissionDocument.objects.filter(file=name).exists() or StudentDocument.objects.filter(document=name).exists() or RTEDocument.objects.filter(document_file=name).exists():
        return
    storage.delete(name)


def schedule_file_cleanup(storage, name):
    def cleanup():
        try:
            delete_unreferenced_file(storage, name)
        except Exception:
            logger.exception("Student document asset cleanup failed for %s", name)
    transaction.on_commit(cleanup)


def save_document_file(document, field, uploaded):
    """Keep the existing file until the database transaction succeeds."""
    file = getattr(document, field)
    old_name, storage = file.name, file.storage
    try:
        file.save(uploaded.name, uploaded, save=False)
        with transaction.atomic():
            document.save()
    except Exception:
        if file.name and file.name != old_name:
            try:
                delete_unreferenced_file(storage, file.name)
            except Exception:
                logger.exception("Failed to clean up an unsuccessful document upload")
        raise
    if old_name != file.name:
        schedule_file_cleanup(storage, old_name)


def document_for_student(student, identifier, lock=False):
    match = re.fullmatch(r"(adm|std|rte)_([0-9]+)", str(identifier))
    if not match:
        from rest_framework.exceptions import NotFound
        raise NotFound("Document not found.")
    source, document_id = match.groups()
    if source == "adm":
        queryset = AdmissionDocument.objects.filter(admission_id=student.admission_id) if student.admission_id else AdmissionDocument.objects.none()
        field = "file"
    elif source == "std":
        queryset = StudentDocument.objects.filter(student=student, school_id=student.school_id)
        field = "document"
    else:
        scope = Q(student=student)
        if student.admission_id:
            scope |= Q(student__isnull=True, admission_id=student.admission_id)
        queryset, field = RTEDocument.objects.filter(scope), "document_file"
    from django.shortcuts import get_object_or_404
    return source, get_object_or_404(queryset.select_for_update() if lock else queryset, pk=document_id), field
