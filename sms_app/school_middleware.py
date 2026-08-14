from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin


class SchoolStatusMiddleware(MiddlewareMixin):
    """
    Middleware to check if the authenticated user's school is active.
    If the school is deactivated, return 403 Forbidden for all requests
    except login/refresh endpoints.
    """

    EXEMPT_PATHS = [
        "/api/access/",  # login
        "/api/api-login/",  # login
        "/api/token/refresh/",  # token refresh
        "/api/send-otp/",  # send OTP
        "/api/verify-otp/",  # verify OTP
    ]

    def process_request(self, request):
        # Skip check for exempt paths
        if any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None

        # Skip for unauthenticated requests (handled by DRF authentication)
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return None

        # Skip for superusers
        if request.user.is_superuser:
            return None

        # Check if user has a school and it's active
        school = getattr(request.user, "school", None)
        if school and school.is_active is False:
            return JsonResponse(
                {"detail": "School is deactivated. Contact administrator."},
                status=403,
            )

        return None