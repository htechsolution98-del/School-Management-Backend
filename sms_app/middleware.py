from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from channels.db import database_sync_to_async


class JWTAuthMiddleware:
    """
    Middleware for JWT authentication in Django Channels WebSocket
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        token = None

        # 1. Try Authorization header
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                auth = value.decode()
                if "Bearer" in auth:
                    token = auth.split(" ")[1]

        # 2. Try query params (fallback)
        if not token:
            query_string = scope.get("query_string", b"").decode()
            params = parse_qs(query_string)
            token = params.get("token", [None])[0]

        scope["user"] = await self.get_user(token)

        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user(self, token):
        if not token:
            return AnonymousUser()

        try:
            jwt_auth = JWTAuthentication()
            validated_token = jwt_auth.get_validated_token(token)
            user = jwt_auth.get_user(validated_token)
            return user
        except:
            return AnonymousUser()