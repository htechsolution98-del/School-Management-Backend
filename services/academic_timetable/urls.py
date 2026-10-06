from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.academic_views import (
    AcademicYearViewSet,
    AcademicYearMainView,
    ClassCategoryViewSet,
    SchoolClassView,
    ClassView,
    SetSubjectView,
    SetDivisionView,
    ListDivisionView,
    SyllabusView,
    AssignClassView,
    TimeTableViewSet,
    AttendanceView,
    BoardMeetingViewSet,
    HomeworkViewSet,
    HomeworkSubmissionViewSet,
)

router = DefaultRouter()
router.register(r"academic-years", AcademicYearViewSet, basename="academic-years")
router.register(r"classcategory", ClassCategoryViewSet, basename="classcategory")
router.register(r"schoolclass", SchoolClassView, basename="schoolclass")
router.register(r"getclass", ClassView, basename="getclass")
router.register(r"timetable", TimeTableViewSet, basename="timetable")
router.register(r"homework", HomeworkViewSet, basename="homework")
router.register(r"homework-submissions", HomeworkSubmissionViewSet, basename="homework-submissions")
router.register(r"board-meetings", BoardMeetingViewSet, basename="board-meetings")

urlpatterns = [
    path("api/v1/academic/", include(router.urls)),
]
