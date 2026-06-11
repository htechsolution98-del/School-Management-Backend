from urllib.parse import parse_qs
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from channels.db import database_sync_to_async


class JWTAuthMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope = dict(scope)

        token = None

        print("HEADERS:", scope.get("headers"))

        for key, value in scope.get("headers", []):
            if key == b"authorization":
                auth = value.decode()
                print("AUTH:", auth)

                if auth.startswith("Bearer "):
                    token = auth.split(" ")[1]
                    print("TOKEN:", token)

        if not token:
            query_string = scope.get("query_string", b"").decode()
            params = parse_qs(query_string)
            token = params.get("token", [None])[0]

        scope["user"] = await self.get_user(token)

        print("USER:", scope["user"])

        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user(self, token):
        if not token:
            return AnonymousUser()

        try:
            jwt_auth = JWTAuthentication()

            validated_token = jwt_auth.get_validated_token(token)
            print("VALIDATED TOKEN:", validated_token)

            user = jwt_auth.get_user(validated_token)
            print("USER FOUND:", user)

            return user

        except Exception as e:
            print("JWT ERROR:", str(e))
            return AnonymousUser()