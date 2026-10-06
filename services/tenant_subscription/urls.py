from django.urls import path, include
from rest_framework.routers import DefaultRouter
from sms_app.subscription_views import (
    SubscriptionPlanViewSet,
    SchoolSubscriptionViewSet,
    SchoolInvoiceViewSet,
    SubscriptionPaymentViewSet,
    SubscriptionAuditLogViewSet,
    SubscriptionSettingViewSet,
)
from sms_app.school_views import (
    SchoolView,
    FeatureView,
    SchoolFeatureView,
    GetFeatureView,
    ChangeFeatureStatusVIew,
)

router = DefaultRouter()
router.register(r"subscription-plans", SubscriptionPlanViewSet, basename="subscription-plans")
router.register(r"school-subscriptions", SchoolSubscriptionViewSet, basename="school-subscriptions")
router.register(r"school-invoices", SchoolInvoiceViewSet, basename="school-invoices")
router.register(r"subscription-payments", SubscriptionPaymentViewSet, basename="subscription-payments")
router.register(r"subscription-audit-logs", SubscriptionAuditLogViewSet, basename="subscription-audit-logs")
router.register(r"subscription-settings", SubscriptionSettingViewSet, basename="subscription-settings")
router.register(r"school", SchoolView, basename="school")
router.register(r"feature", FeatureView, basename="feature")
router.register(r"schoolfeature", SchoolFeatureView, basename="schoolfeature")
router.register(r"getfeature", GetFeatureView, basename="getfeature")
router.register(r"changefeaturestatus", ChangeFeatureStatusVIew, basename="changefeaturestatus")

urlpatterns = [
    path("api/v1/tenant/", include(router.urls)),
]
