from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class TenantHeaderIsolationMiddleware(MiddlewareMixin):
    """
    Middleware to extract and enforce X-School-ID tenant header and check
    school active status across microservices.
    """

    EXEMPT_PATHS = [
        "/api/access/",
        "/api/api-login/",
        "/api/token/refresh/",
        "/api/refresh/",
        "/api/send-otp/",
        "/api/verify-otp/",
        "/health/",
    ]

    def process_request(self, request):
        school_id_header = request.headers.get("X-School-ID")
        if school_id_header:
            try:
                request.tenant_school_id = int(school_id_header)
            except ValueError:
                request.tenant_school_id = None
        else:
            request.tenant_school_id = None

        if any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None

        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        if request.user.is_superuser:
            return None

        school = getattr(request.user, "school", None)
        if school and school.is_active is False:
            return JsonResponse(
                {"detail": "School account is deactivated. Contact administrator."},
                status=403,
            )

        return None
