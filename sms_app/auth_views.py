from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from .models import *
from .serializer import *
from .permissions import *
from .utils import *
import datetime
from django.core.cache import cache
from sms_app.harsh_views import carry_forward_leave

class CustomLoginView(TokenObtainPairView):
    serializer_class = CustomeLoginSerializer

    # def post(self, request, *args, **kwargs):
    #     response = super().post(request, *args, **kwargs)

    #     if response.status_code == 200:
    #         access = response.data.pop('access', None)
    #         refresh = response.data.pop('refresh', None)

    #         response.set_cookie(
    #             key='access_token',
    #             value=access,
    #             httponly=True,
    #             secure=False,  # True in production (HTTPS)
    #             samesite='Lax'
    #         )

    #         response.set_cookie(
    #             key='refresh_token',
    #             value=refresh,
    #             httponly=True,
    #             secure=False,
    #             samesite='Lax'
    #         )

    #     return response


# class CookieTokenRefreshView(TokenRefreshView):
#     def post(self, request, *args, **kwargs):

#         refresh_token = request.COOKIES.get('refresh_token')

#         if not refresh_token:
#             return None

#         request.data['refresh'] = refresh_token

#         response = super().post(request, *args, **kwargs)

#         if response.status_code == 200:
#             access_token = response.get('access')

#             response.set_cookie(
#                 key='access_token',
#                 value=access_token,
#                 httponly=True,
#                 secure=False,
#                 samesite='Lax'
#             )

#         return response


# ====== CODE for GENERATE ID & CODE =====


class SendOTPView(APIView):
    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        mobile = serializer.validated_data.get("mobile")

        if not email and not mobile:
            return Response(
                {"error": "Provide email or mobile"}, status=status.HTTP_400_BAD_REQUEST
            )

        if email and mobile:
            return Response(
                {"error": "Just User email or mobile"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if email:
            if User.objects.filter(email=email).exists():
                return Response(
                    {"error": "User with this email already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if mobile:
            if User.objects.filter(mobile=mobile).exists():
                return Response(
                    {"error": "User with this mobile already exists"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        otp = str(random.randint(100000, 999999))

        OTP.objects.create(
            email=email if email else None, mobile=mobile if mobile else None, otp=otp
        )

        # if email:
        #     send_otp_email(
        #         email=email,
        #         otp=otp

        #     )
        # if email:
        # send_mail(
        #     subject="Your OTP Code",
        #     message=f"Your OTP is {otp}. It is valid for 5 minutes.",
        #     from_email=",
        #     recipient_list=[email],
        # )

        return Response(
            {"message": "OTP sent successfully", "otp": otp}  # remove in production
        )




class VerifyOTPView(APIView):
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        return Response(
            {
                "message": "User registered successfully",
            },
            status=status.HTTP_201_CREATED,
        )


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

# from .serializers import LoginSerializer
from .models import UserModuleAccess
from datetime import date



class LoginView(APIView):

    def post(self, request):

        # =====================================
        # Validate User
        # =====================================
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        
        # user_block = User.objects.filter(username=user).first()
        # print("...........",user_block)
        
        staff = Staff.objects.filter(user=user).first()

        if staff:
            # with transaction.atomic():
            carry_forward_leave(staff)

        # =====================================
        # Generate JWT Tokens
        # =====================================
        refresh = RefreshToken.for_user(user)

        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        # =====================================
        # Roles
        # =====================================
        roles = list(user.groups.values_list("name", flat=True))
        if getattr(user, "is_superuser", False):
            if "super_admin" not in roles:
                roles.append("super_admin")
        
        if not roles and getattr(user, "role", None):
            roles = [user.role]
        if not roles:
            roles = ["temp_user"]

        # =====================================
        # Modules
        # =====================================
        modules = list(
            UserModuleAccess.objects.filter(user=user).values_list(
                "module__code", flat=True
            )
        )

        # =====================================
        # Common Payload
        # =====================================
        response_data = {
            "access": access_token,
            "refresh": refresh_token,
            "school_id": user.school.id if user.school else None,
            "school_name": user.school.name if user.school else None,
            "school_slug": user.school.slug if user.school else None,
            "roles": roles,
            "modules": modules,
        }

        # =====================================
        # Detect Client Type
        # =====================================
        client_type = request.headers.get("Client-Type", "web").lower()

        # =====================================
        # MOBILE / ANDROID
        # Return Tokens in JSON
        # =====================================
        if client_type in ["mobile", "android"]:

            return Response(response_data, status=status.HTTP_200_OK)

        # =====================================
        # WEB & ALL CLIENTS
        # Store Tokens in Cookies and Return in Body for Header Auth
        # =====================================
        is_secure = request.is_secure()
        samesite = "None" if is_secure else "Lax"

        response = Response(
            {
                "access": access_token,
                "refresh": refresh_token,
                "school_id": response_data["school_id"],
                "school_name": response_data["school_name"],
                "school_slug": response_data["school_slug"],
                "roles": response_data["roles"],
                "modules": response_data["modules"],
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=False,
            secure=is_secure,
            samesite=samesite,
            max_age=60 * 60,
            path="/",
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=False,
            secure=is_secure,
            samesite=samesite,
            max_age=7 * 24 * 60 * 60,
            path="/",
        )

        return response




class UserListView(generics.ListAPIView):
    queryset = User.objects.all()
    serializer_class = UserListSerialzer

    def get_queryset(self):
        school = self.request.user.school
        return User.objects.filter(school=school)




class ModuleView(ModelViewSet):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        school = self.request.user.school
        enabled_feature_ids = SchoolFeature.objects.filter(
            school=school,
            is_enabled=True,
        ).values_list("feature_id", flat=True)

        return Module.objects.filter(
            for_role_id__in=enabled_feature_ids,
            is_active=True,
        )




class ChangeModuleView(ModelViewSet):
    queryset = UserModuleAccess.objects.all()
    serializer_class = ChangeFeatureStatusSerializer
    http_method_names = ["get", "post", "delete"]


# =========PERMISSIONS===========

from django.core.management import call_command
from rest_framework import permissions

class InitDatabaseView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            call_command("create_admin")
            return Response({"message": "Database initialized, Superadmin created, and Features seeded successfully!"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





