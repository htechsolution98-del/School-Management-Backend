from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from rest_framework.permissions import BasePermission
from django.utils import timezone
from datetime import timedelta

from .models import SchoolSubscription, SubscriptionPlanModule, Student, SubscriptionSetting


class HasActiveSubscription(BasePermission):
    """
    DRF Permission class ensuring user's school has a valid, active trial or subscription.
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        # Superadmins bypass subscription check
        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            return True

        school = getattr(user, "school", None)
        if not school:
            # User without school (e.g. platform admin)
            return True

        # Fetch subscription
        try:
            sub = school.subscription
        except SchoolSubscription.DoesNotExist:
            return False

        # Status check
        if sub.status in ["SUSPENDED", "CANCELLED", "TRIAL_EXPIRED", "EXPIRED"]:
            return False

        # Expiry + Grace period check
        today = timezone.now().date()
        effective_due = sub.due_date + timedelta(days=sub.grace_period_days)
        return today <= effective_due


class HasPlanModulePermission(BasePermission):
    """
    DRF Permission class verifying that the user's school subscription plan includes the target module.
    Usage in ViewSet:
        permission_classes = [HasPlanModulePermission]
        module_code = "FEES"
    """

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            return True

        school = getattr(user, "school", None)
        if not school:
            return True

        module_code = getattr(view, "module_code", None)
        if not module_code:
            return True

        try:
            sub = school.subscription
        except SchoolSubscription.DoesNotExist:
            return False

        if not sub.is_valid_now():
            return False

        if not sub.plan:
            # If no explicit plan assigned (e.g. legacy default trial), grant access by default
            return True

        # Check if plan contains module
        return SubscriptionPlanModule.objects.filter(
            plan=sub.plan,
            module__code=module_code,
            is_enabled=True
        ).exists()


class CheckStudentLimit(BasePermission):
    """
    DRF Permission class that blocks student creation (POST) if the school student limit is reached.
    """

    def has_permission(self, request, view):
        if request.method != "POST":
            return True

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False):
            return True

        school = getattr(user, "school", None)
        if not school:
            return True

        try:
            sub = school.subscription
        except SchoolSubscription.DoesNotExist:
            return True

        if not sub.plan or sub.plan.max_students == 0:
            return True  # 0 means unlimited

        active_students = Student.objects.filter(school=school, is_active=True).count()
        if active_students >= sub.plan.max_students:
            self.message = f"Student limit of {sub.plan.max_students} reached for your subscription plan ({sub.plan.name}). Please upgrade your plan."
            return False

        return True


class SubscriptionAccessMiddleware(MiddlewareMixin):
    """
    Django middleware enforcing subscription status on protected API endpoints.
    Allowed paths for expired/suspended schools:
    - Login / Auth (/api/api-login/, /api/send-otp/, /api/verify-otp/, /api/token/refresh/)
    - Subscription APIs (/api/subscription/, /api/admin/)
    - Support / Profile endpoints
    """

    EXEMPT_PREFIXES = [
        "/api/api-login/",
        "/api/send-otp/",
        "/api/verify-otp/",
        "/api/token/refresh/",
        "/api/subscription/",
        "/api/admin/subscription/",
        "/admin/",
        "/static/",
        "/media/",
        "/swagger/",
        "/redoc/",
    ]

    def process_request(self, request):
        path = request.path

        # Check if path is exempt
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return None

        # Non-API requests (e.g., frontend pages served separately)
        if not path.startswith("/api/"):
            return None

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            return None

        school = getattr(user, "school", None)
        if not school:
            return None

        try:
            sub = school.subscription
        except SchoolSubscription.DoesNotExist:
            return None

        # Check subscription status & validity
        if not sub.is_valid_now():
            # Get enforcement mode setting (BLOCK vs READ_ONLY)
            try:
                enforcement_mode = SubscriptionSetting.objects.get(key="SUBSCRIPTION_ENFORCEMENT_MODE").value
            except SubscriptionSetting.DoesNotExist:
                enforcement_mode = "BLOCK"

            if enforcement_mode == "READ_ONLY" and request.method in ["GET", "HEAD", "OPTIONS"]:
                return None

            return JsonResponse(
                {
                    "error": "SUBSCRIPTION_REQUIRED",
                    "detail": "Your school subscription has expired or is suspended. Please upgrade or renew your plan.",
                    "subscription_status": sub.status,
                    "due_date": str(sub.due_date),
                },
                status=403,
            )

        return None
