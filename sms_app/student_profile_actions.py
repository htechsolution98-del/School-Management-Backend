import logging
import mimetypes
from pathlib import Path
from django.http import FileResponse
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import AdmissionDocument, DocumentField, RTEDocument, StudentDocument, SchoolProfileField, School
from .student_profile_serializers import StudentDocumentMetadataSerializer
from .student_profile_services import document_for_student, validate_upload, save_document_file, schedule_file_cleanup, profile_queryset, delete_unreferenced_file

logger = logging.getLogger(__name__)


class StudentProfileActionsMixin:
    def refreshed_profile(self, student):
        current = profile_queryset(type(student).objects.filter(pk=student.pk, school_id=student.school_id)).get()
        return self.get_serializer(current).data

    @action(detail=False, methods=["post"], url_path="profile-fields")
    def create_profile_field(self, request):
        school_id = getattr(request.user, "school_id", None)
        if not school_id:
            raise ValidationError({"detail": "A school is required."})
        label = " ".join(str(request.data.get("label", "")).split())
        kind = request.data.get("kind")
        if not label or len(label) > 100 or kind not in {"ID", "DOCUMENT"}:
            raise ValidationError({"detail": "Enter a field name up to 100 characters and a valid category."})
        if kind == "ID" and label.casefold() in {"aadhaar", "aadhaar number", "aadhar number", "abc", "abc / apaar id", "udise / pen"}:
            raise ValidationError({"detail": "This ID field already exists."})
        with transaction.atomic():
            School.objects.select_for_update().get(pk=school_id)
            field, created = SchoolProfileField.objects.get_or_create(school_id=school_id, kind=kind, key=label.casefold(), defaults={"label": label})
        if not created:
            return Response({"detail": "A field with this name already exists."}, status=409)
        return Response({"id": field.id, "label": field.label, "kind": field.kind}, status=201)

    @action(detail=True, methods=["get"], url_path=r"documents/(?P<document_key>(?:adm|std|rte)_[0-9]+)/content")
    def profile_document_content(self, request, pk=None, document_key=None):
        student = self.get_object()
        _, document, field = document_for_student(student, document_key)
        file = getattr(document, field)
        if not file:
            return Response({"detail": "This document has no uploaded file."}, status=404)
        filename = Path(file.name).name
        try:
            from cloudinary_storage.storage import MediaCloudinaryStorage
            if isinstance(file.storage, MediaCloudinaryStorage):
                import cloudinary.api
                import cloudinary.utils
                import requests
                storage = file.storage
                resource_type = storage._get_resource_type(file.name)
                public_id = storage._prepend_prefix(file.name)
                resource = cloudinary.api.resource(public_id, resource_type=resource_type)
                file_format = resource.get("format") or Path(filename).suffix.lstrip(".")
                url = cloudinary.utils.private_download_url(public_id, file_format, resource_type=resource_type, type=resource.get("type", "upload"), attachment=False)
                upstream = requests.get(url, timeout=(5, 30))
                upstream.raise_for_status()
                content = ContentFile(upstream.content)
                if file_format and not filename.lower().endswith("." + file_format.lower()):
                    filename += "." + file_format
            else:
                content = file.open("rb")
            response = FileResponse(content, filename=filename, as_attachment=request.query_params.get("download") == "1", content_type=mimetypes.guess_type(filename)[0] or "application/octet-stream")
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        except FileNotFoundError:
            return Response({"detail": "The stored file was not found. Please replace this document."}, status=404)
        except Exception:
            logger.exception("Student document retrieval failed for %s", document_key)
            return Response({"detail": "The file could not be retrieved from storage. Please retry or replace the document."}, status=502)

    @action(detail=True, methods=["get", "post"], url_path="documents")
    def profile_documents(self, request, pk=None):
        student = self.get_object()
        if request.method == "GET":
            return Response(self.get_serializer(student).data["documents"])
        source = request.data.get("source", "std")
        if source not in {"adm", "std", "rte"}:
            raise ValidationError({"source": "Unknown document source."})
        uploaded = validate_upload(request.FILES.get("file"))
        metadata = StudentDocumentMetadataSerializer(data=request.data, context={"source": source})
        metadata.is_valid(raise_exception=True)
        data = metadata.validated_data
        profile_field = None
        if request.data.get("profile_field"):
            if source != "std":
                raise ValidationError({"profile_field": "Choose a student record for shared documents."})
            profile_field = get_object_or_404(SchoolProfileField, pk=request.data["profile_field"], school_id=student.school_id, kind="DOCUMENT")
        document = None
        file_field = "file" if source == "adm" else "document_file" if source == "rte" else "document"
        try:
            with transaction.atomic():
                # Serializes uploads to the same required admission slot without a new schema/duplicate records.
                type(student).objects.select_for_update().get(pk=student.pk, school_id=student.school_id)
                if profile_field and StudentDocument.objects.filter(student=student, profile_field=profile_field).exists():
                    return Response({"detail": "This document is already uploaded. Use Replace."}, status=409)
                if source == "adm":
                    if not student.admission_id:
                        raise ValidationError({"document_field": "This student has no admission form."})
                    try:
                        slot_id = int(request.data.get("document_field", ""))
                    except (TypeError, ValueError):
                        raise ValidationError({"document_field": "Select a valid admission document slot."})
                    slot = get_object_or_404(DocumentField, pk=slot_id, school_id=student.school_id, form_id=student.admission.form_id)
                    if AdmissionDocument.objects.filter(admission_id=student.admission_id, document_field=slot).exists():
                        raise ValidationError({"document_field": "A document already exists in this slot. Use Replace on that document."})
                    document = AdmissionDocument(admission_id=student.admission_id, school_id=student.school_id, document_field=slot)
                else:
                    if profile_field:
                        data["title"] = profile_field.label
                    if not data.get("title"):
                        raise ValidationError({"title": "Document name is required."})
                    if source == "rte":
                        document = RTEDocument(student=student, document_name=data["title"], expiry_date=data.get("expiry_date"))
                    else:
                        document = StudentDocument(student=student, profile_field=profile_field, school_id=student.school_id, uploaded_by=getattr(request.user, "staff", None), title=data["title"], document_type=data.get("document_type", "OTHER"), description=data.get("description"))
                save_document_file(document, file_field, uploaded)
                result = self.refreshed_profile(student)
        except Exception:
            if document:
                file = getattr(document, file_field)
                if file.name:
                    try:
                        delete_unreferenced_file(file.storage, file.name)
                    except Exception:
                        logger.exception("Failed to clean up unsuccessful student document creation")
            raise
        return Response(result, status=201)

    @action(detail=True, methods=["patch", "delete"], url_path=r"documents/(?P<document_key>(?:adm|std|rte)_[0-9]+)")
    def profile_document(self, request, pk=None, document_key=None):
        student = self.get_object()
        new_file = None
        try:
            with transaction.atomic():
                source, document, field = document_for_student(student, document_key, lock=True)
                current_file = getattr(document, field)
                expected = request.data.get("expected_file")
                if expected is not None and expected != current_file.name:
                    return Response({"detail": "The document has changed. Refresh before editing it."}, status=409)
                if request.method == "DELETE":
                    storage, name = current_file.storage, current_file.name
                    document.delete()
                    schedule_file_cleanup(storage, name)
                else:
                    metadata = StudentDocumentMetadataSerializer(data=request.data, context={"source": source})
                    metadata.is_valid(raise_exception=True)
                    data = metadata.validated_data
                    verification = data.pop("is_verified", None)
                    if "is_verified" not in request.data:
                        verification = None
                    if verification is not None:
                        if request.FILES.get("file"):
                            raise ValidationError({"is_verified": "Review the replacement file before verifying it."})
                        if verification and not current_file:
                            raise ValidationError({"is_verified": "Upload a file before verifying this document."})
                        document.is_verified = verification
                        document.verified_at = timezone.now() if verification else None
                        document.verified_by = request.user if verification else None
                    for key, value in data.items():
                        setattr(document, "document_name" if source == "rte" and key == "title" else key, value)
                    if request.FILES.get("file"):
                        uploaded = validate_upload(request.FILES["file"])
                        document.is_verified = False
                        document.verified_by = None
                        document.verified_at = None
                        old_name = current_file.name
                        save_document_file(document, field, uploaded)
                        current_file = getattr(document, field)
                        if current_file.name != old_name:
                            new_file = (current_file.storage, current_file.name)
                    else:
                        if not data and verification is None:
                            raise ValidationError({"detail": "Provide a replacement file or editable document metadata."})
                        document.save()
                result = self.refreshed_profile(student)
        except Exception:
            if new_file:
                try:
                    delete_unreferenced_file(*new_file)
                except Exception:
                    logger.exception("Failed to clean up rolled-back replacement upload")
            raise
        return Response(result)
