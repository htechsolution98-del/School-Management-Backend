from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.exam_views import (
    ResultWeightageViewSet,
    ExamRoomViewSet,
    ExamTermViewSet,
    ExamFullViewSet,
    SeatingAllocationViewSet,
    SubjectMarksEntryViewSet,
    TeacherAssessmentViewSet,
    ClassTeacherVerificationViewSet,
)

router = DefaultRouter()
router.register(r"result-weightage", ResultWeightageViewSet, basename="result-weightage")
router.register(r"exam-rooms", ExamRoomViewSet, basename="exam-rooms")
router.register(r"exam-terms", ExamTermViewSet, basename="exam-terms")
router.register(r"exams", ExamFullViewSet, basename="exams")
router.register(r"seating-allocations", SeatingAllocationViewSet, basename="seating-allocations")

urlpatterns = [
    path("api/v1/examination/", include(router.urls)),
]
