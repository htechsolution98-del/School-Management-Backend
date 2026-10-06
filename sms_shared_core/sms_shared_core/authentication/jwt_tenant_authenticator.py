from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class CookieJWTTenantAuthentication(JWTAuthentication):
    """
    Cookie & Header JWT Authenticator for Multi-Tenant School Microservices.
    Extracts access token from Authorization HTTP Header or HTTP-Only cookie,
    validates user credentials, and enforces school activation checks.
    """

    def authenticate(self, request):
        header = self.get_header(request)

        if header is not None:
            raw_token = self.get_raw_token(header)
        else:
            raw_token = request.COOKIES.get("access_token")

        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        user = self.get_user(validated_token)

        is_super = (
            user.is_superuser
            or user.is_staff
            or getattr(user, "role", "").lower() in ["superadmin", "super_admin"]
        )

        if not is_super:
            school = getattr(user, "school", None)
            if school and school.is_active is False:
                raise AuthenticationFailed(
                    {"detail": "School account is deactivated. Contact administrator."}
                )

        return user, validated_token
