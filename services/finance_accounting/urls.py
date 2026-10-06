from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.finance_views import (
    FeeTypeViewSet,
    FeeWiseClassViewSet,
    SalaryComponentViewSet,
    StaffSalaryComponentViewSet,
    StaffSalaryPaymentViewSet,
    StudentFeeViewSet,
    StudentFeePaymentViewSet,
    FeeVerifyView,
)

router = DefaultRouter()
router.register(r"fee-types", FeeTypeViewSet, basename="fee-types")
router.register(r"fee-wise-class", FeeWiseClassViewSet, basename="fee-wise-class")
router.register(r"salary-components", SalaryComponentViewSet, basename="salary-components")
router.register(r"staff-salary-components", StaffSalaryComponentViewSet, basename="staff-salary-components")
router.register(r"staff-salary-payments", StaffSalaryPaymentViewSet, basename="staff-salary-payments")
router.register(r"student-fees", StudentFeeViewSet, basename="student-fees")
router.register(r"student-fee-payments", StudentFeePaymentViewSet, basename="student-fee-payments")

urlpatterns = [
    path("api/v1/finance/", include(router.urls)),
]
