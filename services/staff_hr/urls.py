from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.staff_views import (
    DepartmentViewSet,
    StaffView,
    StaffListView,
    GetTeacherView,
)
from sms_app.library_leave_views import (
    LeaveTemplateViewSet,
    LeaveTypeViewSet,
    LeaveRequestView,
    GetLeaveRequestView,
    ChangeLeaveView,
)

router = DefaultRouter()
router.register(r"departments", DepartmentViewSet, basename="departments")
router.register(r"staff", StaffView, basename="staff")
router.register(r"staff-list", StaffListView, basename="staff-list")
router.register(r"leave-templates", LeaveTemplateViewSet, basename="leave-templates")
router.register(r"leave-types", LeaveTypeViewSet, basename="leave-types")

urlpatterns = [
    path("api/v1/staff-hr/", include(router.urls)),
]
