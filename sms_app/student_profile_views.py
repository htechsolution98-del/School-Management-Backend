from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Student, StudentExtraData, AdmissionDocument, StudentDocument, RTEDocument, StudentDocumentReview


class CanManageStudentProfiles(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        roles = {str(role).strip().lower() for role in user.groups.values_list("name", flat=True)}
        roles.add((getattr(user, "role", "") or "").strip().lower())
        return user.is_superuser or bool(roles & {"clerk", "fees_clerk", "principal", "super_admin", "superadmin"})


def students_for(user):
    if not user.school_id:
        raise PermissionDenied("Your account must be assigned to a school.")
    return Student.objects.filter(school_id=user.school_id).select_related("school_class", "academic_year", "admission")


def student_row(student):
    return {
        "id": student.id, "name": " ".join(filter(None, [student.name, student.surname])),
        "gr_no": student.gr_no, "roll_no": student.roll_no, "mobile": student.mobile,
        "class_name": student.school_class.school_class if student.school_class else "Unassigned",
        "division": student.division, "academic_year": student.academic_year.name if student.academic_year else None,
        "is_active": student.is_active, "is_rte": student.is_rte, "created_at": student.created_at,
    }


def document_sources(student):
    admission = AdmissionDocument.objects.filter(admission_id=student.admission_id).select_related("document_field") if student.admission_id else AdmissionDocument.objects.none()
    rte_filter = Q(student=student)
    if student.admission_id:
        rte_filter |= Q(student__isnull=True, admission_id=student.admission_id)
    return {
        "admission": (admission, "file"),
        "student": (StudentDocument.objects.filter(student=student, school_id=student.school_id), "document"),
        "rte": (RTEDocument.objects.filter(rte_filter), "document_file"),
    }


def documents_for(student, request):
    reviews = {(review.source, review.document_id): review for review in StudentDocumentReview.objects.filter(student=student).select_related("reviewed_by")}
    documents = []
    for source, (queryset, file_field) in document_sources(student).items():
        for document in queryset:
            file = getattr(document, file_field)
            review = reviews.get((source, document.id))
            current_review = review if review and review.file_name == file.name else None
            label = document.document_field.label if source == "admission" else document.title if source == "student" else document.document_name
            documents.append({
                "id": document.id, "source": source, "label": label, "file_name": file.name,
                "url": request.build_absolute_uri(file.url) if file else None,
                "status": current_review.status if current_review else "verified" if source == "rte" and document.is_verified and review is None else "pending",
                "note": current_review.note if current_review else "",
                "reviewed_by": current_review.reviewed_by.get_full_name() or current_review.reviewed_by.username if current_review and current_review.reviewed_by else None,
                "reviewed_at": current_review.reviewed_at if current_review else None,
            })
    return documents


class ClerkStudentProfilesView(APIView):
    permission_classes = [IsAuthenticated, CanManageStudentProfiles]

    def get(self, request, student_id=None):
        queryset = students_for(request.user)
        if student_id is None:
            return Response([student_row(student) for student in queryset.order_by("name", "id")])
        student = get_object_or_404(queryset, pk=student_id)
        result = student_row(student)
        result["details"] = model_to_dict(student, exclude=["user", "school", "school_class", "academic_year", "admission"])
        extra = StudentExtraData.objects.filter(student=student).first()
        result["extra_details"] = model_to_dict(extra, exclude=["student", "id"]) if extra else {}
        fields = {}
        if student.admission_id:
            for value in student.admission.field_values.select_related("field", "field__section").order_by("id"):
                fields[value.field_id] = {"label": value.field.label, "section": value.field.section.title, "value": value.value}
        for value in student.field_values.select_related("field", "field__section").order_by("id"):
            fields[value.field_id] = {"label": value.field.label, "section": value.field.section.title, "value": value.value}
        result["fields"] = list(fields.values())
        result["admission_number"] = student.admission.admission_number if student.admission else None
        result["documents"] = documents_for(student, request)
        return Response(result)


class ClerkStudentDocumentReviewView(APIView):
    permission_classes = [IsAuthenticated, CanManageStudentProfiles]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    @transaction.atomic
    def patch(self, request, student_id, source, document_id):
        student = get_object_or_404(students_for(request.user), pk=student_id)
        sources = document_sources(student)
        if source not in sources:
            raise ValidationError("Unknown document source.")
        queryset, file_field = sources[source]
        document = get_object_or_404(queryset.select_for_update(), pk=document_id)
        file = getattr(document, file_field)
        if request.data.get("file_name") != file.name:
            return Response({"detail": "The document has changed. Refresh the profile before reviewing it."}, status=409)
        action = request.data.get("action")
        note = str(request.data.get("note", "")).strip()
        if action not in {"verify", "requires_reupload", "reupload"}:
            raise ValidationError("Choose verify, requires_reupload or reupload.")
        if action == "verify" and not file:
            raise ValidationError("Upload a document before verifying it.")
        if action == "requires_reupload" and not note:
            raise ValidationError("Please explain the issue with this document.")
        if action == "reupload":
            uploaded = request.FILES.get("file")
            if not uploaded:
                raise ValidationError("Select the replacement document.")
            if uploaded.size > 10 * 1024 * 1024:
                raise ValidationError("Maximum file size is 10 MB.")
            header = uploaded.read(16)
            uploaded.seek(0)
            valid = header.startswith(b"%PDF-") or header.startswith(b"\xff\xd8\xff") or header.startswith(b"\x89PNG\r\n\x1a\n") or (header[:4] == b"RIFF" and header[8:12] == b"WEBP")
            if not valid:
                raise ValidationError("Upload a PDF, JPG, PNG or WebP document.")
            setattr(document, file_field, uploaded)
            document.save(update_fields=[file_field])
            file = getattr(document, file_field)
        state = "verified" if action == "verify" else "requires_reupload" if action == "requires_reupload" else "pending"
        if source == "rte":
            document.is_verified = state == "verified"
            document.save(update_fields=["is_verified"])
        StudentDocumentReview.objects.update_or_create(
            student=student, source=source, document_id=document.id,
            defaults={"file_name": file.name, "status": state, "note": note, "reviewed_by": request.user, "reviewed_at": timezone.now()},
        )
        return Response({"documents": documents_for(student, request), "message": "Replacement uploaded. Verify the new file." if action == "reupload" else "Document review saved."})
