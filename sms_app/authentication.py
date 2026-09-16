
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):

        # =====================================
        # First Check Authorization Header
        # =====================================
        header = self.get_header(request)

        if header is not None:

            raw_token = self.get_raw_token(header)

        else:

            # =====================================
            # If Header Missing
            # Check Cookie
            # =====================================
            raw_token = request.COOKIES.get("access_token")

        # =====================================
        # No Token Found
        # =====================================
        if raw_token is None:
            return None

        # =====================================
        # Validate Token
        # =====================================
        validated_token = self.get_validated_token(raw_token)

        # =====================================
        # Return Authenticated User
        # =====================================
        user = self.get_user(validated_token)

        # =====================================
        # Block Users Of Deactivated Schools
        # =====================================
        is_super = user.is_superuser or user.is_staff or getattr(user, "role", "").lower() in ["superadmin", "super_admin"]
        if not is_super:
            school = getattr(user, "school", None)
            if school and school.is_active is False:
                raise AuthenticationFailed(
                    {"message": "School is deactivated. Contact administrator."}
                )


        return user, validated_token