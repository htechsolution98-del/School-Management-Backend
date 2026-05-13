
from rest_framework_simplejwt.authentication import JWTAuthentication


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
        return self.get_user(validated_token), validated_token