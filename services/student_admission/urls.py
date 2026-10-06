from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.student_views import (
    AdmissionFormViewSet,
    FormStatus,
    ManualStudentView,
    FormSubmissionViewSet,
    RTEDocumentViewSet,
    DocumentSubmissionView,
    TempUserAdmissionViewSet,
    TempUserListViewSet,
    AdmissionReadOnlyViewSet,
    AdmissionReceiptViewSet,
    AdmissionUpdateViewSet,
    AdmissionDocumentViewSet,
    ClerkVerifyView,
    GetStudentView,
)

router = DefaultRouter()
router.register(r"forms", AdmissionFormViewSet, basename="forms")
router.register(r"form-submissions", FormSubmissionViewSet, basename="form-submissions")
router.register(r"rte-documents", RTEDocumentViewSet, basename="rte-documents")
router.register(r"students", GetStudentView, basename="students")
router.register(r"temp-users", TempUserListViewSet, basename="temp-users")

urlpatterns = [
    path("api/v1/student/", include(router.urls)),
]
