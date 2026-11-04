from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework import permissions
from rest_framework.viewsets import ModelViewSet
from rest_framework import generics
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from .models import *
from .serializer import *
from .serializer import _user_display_name
from .permissions import *
from .utils import *
import datetime
import re
from django.core.cache import cache
from sms_app.library_leave_views import carry_forward_leave

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


class CookieTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh") or request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token is required.", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        data["refresh"] = refresh_token

        serializer = self.get_serializer(data=data)

        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            return Response(
                {"detail": "Token is invalid or expired", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Check if user account is active before issuing refreshed tokens
        from rest_framework_simplejwt.tokens import RefreshToken
        from django.contrib.auth import get_user_model
        try:
            r_token = RefreshToken(refresh_token)
            uid = r_token.payload.get("user_id")
            if uid:
                u = get_user_model().objects.filter(id=uid).first()
                if not u or not u.is_active:
                    err_res = Response(
                        {"detail": "User account is inactive. Please contact administrator.", "code": "user_inactive"},
                        status=status.HTTP_401_UNAUTHORIZED,
                    )
                    err_res.delete_cookie("access_token")
                    err_res.delete_cookie("refresh_token")
                    return err_res
        except Exception:
            pass

        token_data = serializer.validated_data
        access_token = token_data.get("access")

        is_secure = request.is_secure()
        samesite = "None" if is_secure else "Lax"

        response = Response(token_data, status=status.HTTP_200_OK)
        if access_token:
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=is_secure,
                samesite=samesite,
                max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            )

        rotated_refresh = token_data.get("refresh")
        if rotated_refresh:
            response.set_cookie(
                key="refresh_token",
                value=rotated_refresh,
                httponly=True,
                secure=is_secure,
                samesite=samesite,
                max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
            )

        return response


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
                {"error": "Provide either email or mobile"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        clean_mobile = "".join(filter(str.isdigit, str(mobile or "")))
        if len(clean_mobile) > 10:
            clean_mobile = clean_mobile[-10:]

        # For administrative staff/principals/trustees, prevent public OTP overwrite
        if clean_mobile:
            admin_user = User.objects.filter(
                Q(mobile=clean_mobile) | Q(username=clean_mobile),
                Q(is_staff=True) | Q(is_superuser=True) | Q(role__in=["admin(trustee)", "principal", "clerk", "teacher"])
            ).first()
            if admin_user:
                return Response(
                    {"error": "An administrative account with this mobile already exists. Please sign in."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if email:
            admin_user = User.objects.filter(
                Q(is_staff=True) | Q(is_superuser=True) | Q(role__in=["admin(trustee)", "principal", "clerk", "teacher"]),
                email=email,
            ).first()
            if admin_user:
                return Response(
                    {"error": "An administrative account with this email already exists. Please sign in."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        otp = str(random.randint(100000, 999999))

        OTP.objects.create(
            email=email if email else None,
            mobile=clean_mobile if clean_mobile else (mobile if mobile else None),
            otp=otp
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
        # Resolve School (including Student / Parent lookups)
        # =====================================
        school_obj = getattr(user, "school", None) or getattr(user, "managed_school", None)
        if not school_obj:
            try:
                student_obj = Student.objects.filter(user=user).select_related("school").first()
                if not student_obj and getattr(user, "username", None):
                    student_obj = Student.objects.filter(gr_no=user.username).select_related("school").first()
                if student_obj and student_obj.school:
                    school_obj = student_obj.school
            except Exception:
                pass
        if not school_obj:
            try:
                parent_obj = Perents.objects.filter(user=user).select_related("perents_of__school").first()
                if parent_obj and parent_obj.perents_of and parent_obj.perents_of.school:
                    school_obj = parent_obj.perents_of.school
            except Exception:
                pass

        # =====================================
        # Common Payload
        # =====================================
        response_data = {
            "access": access_token,
            "refresh": refresh_token,
            "school_id": school_obj.id if school_obj else (user.school.id if user.school else None),
            "school_name": school_obj.name if school_obj else (user.school.name if user.school else None),
            "school_slug": school_obj.slug if school_obj else (user.school.slug if user.school else None),
            "roles": roles,
            "modules": modules,
            "user": {
                "id": user.id,
                "username": user.username,
                "name": _user_display_name(user),
                "email": user.email,
                "mobile": user.mobile,
                "roles": roles,
                "school_id": school_obj.id if school_obj else None,
                "school_name": school_obj.name if school_obj else None,
            },
        }

        # Log authentication activity
        try:
            from .activity_logger import log_activity
            display_name = _user_display_name(user)
            role_label = roles[0].title() if roles else "User"
            log_activity(
                user=user,
                action="LOGIN",
                module="AUTH",
                title=f"{display_name} ({role_label}) Signed In",
                description=f"User {user.username} ({display_name}) successfully signed in to {school_obj.name if school_obj else 'the portal'}.",
                school=school_obj,
                extra_data={
                    "user_id": user.id,
                    "username": user.username,
                    "display_name": display_name,
                    "roles": roles,
                    "school_id": school_obj.id if school_obj else None,
                    "school_name": school_obj.name if school_obj else None,
                    "client_type": request.headers.get("Client-Type", "web"),
                },
                request=request,
            )
        except Exception:
            pass

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

        response = Response(response_data, status=status.HTTP_200_OK)

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


class LogoutView(APIView):
    """
    POST /api/logout/ - Logs out the user, records LOGOUT activity, and clears auth cookies.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            user_id = request.data.get("user_id")
            username = request.data.get("username")
            if user_id:
                user = CustomUser.objects.filter(id=user_id).first()
            elif username:
                user = CustomUser.objects.filter(username=username).first()

        if user and (getattr(user, "is_authenticated", False) or getattr(user, "id", None)):
            try:
                from .activity_logger import log_activity
                display_name = _user_display_name(user)
                roles = list(user.groups.values_list("name", flat=True))
                role_label = roles[0].title() if roles else (str(getattr(user, "role", "") or "User").title())
                school_obj = getattr(user, "school", None) or getattr(user, "managed_school", None)
                log_activity(
                    user=user,
                    action="LOGOUT",
                    module="AUTH",
                    title=f"{display_name} ({role_label}) Signed Out",
                    description=f"User {user.username} logged out from the portal session.",
                    school=school_obj,
                    extra_data={
                        "user_id": user.id,
                        "username": user.username,
                        "role": role_label,
                        "school_id": school_obj.id if school_obj else None,
                        "school_name": school_obj.name if school_obj else None,
                    },
                    request=request,
                )
            except Exception:
                pass

        response = Response({"message": "Successfully logged out."}, status=status.HTTP_200_OK)
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
        return response


class CurrentUserProfileView(APIView):
    """
    GET /api/me/ — profile of the currently authenticated user.

    The user is resolved from the request token, so this works for every role
    and can never expose another account's data.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CurrentUserProfileSerializer(
            request.user, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """
    POST /api/change-password/
    Allows any user in any role (Principal, Teacher, Student, Parent, Clerk, etc.)
    to change their password after verifying their current password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        current_password = str(request.data.get("current_password") or "").strip()
        new_password = str(request.data.get("new_password") or "").strip()
        confirm_password = str(request.data.get("confirm_password") or "").strip()

        if not current_password:
            return Response(
                {"error": "Current password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not new_password:
            return Response(
                {"error": "New password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Disallow identical current and new password
        if current_password == new_password or user.check_password(new_password):
            return Response(
                {"error": "Current password and new password cannot be the same. Please choose a different password."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Strong password validation rules
        if len(new_password) < 8:
            return Response(
                {"error": "New password must be at least 8 characters long."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not re.search(r"[A-Z]", new_password):
            return Response(
                {"error": "New password must contain at least one uppercase letter (A-Z)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not re.search(r"[a-z]", new_password):
            return Response(
                {"error": "New password must contain at least one lowercase letter (a-z)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not re.search(r"\d", new_password):
            return Response(
                {"error": "New password must contain at least one number (0-9)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_+=\[\]\\;'`~]", new_password):
            return Response(
                {"error": "New password must contain at least one special character (!@#$%^&* etc.)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_password != confirm_password:
            return Response(
                {"error": "New password and confirmation password do not match."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Verify current password using standard Django hasher
        if not user.check_password(current_password):
            return Response(
                {"error": "Current password is incorrect. Please verify and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hash and store new password
        user.set_password(new_password)
        user.save()

        # Record activity log
        from .activity_logger import log_activity
        log_activity(
            user=user,
            action="PASSWORD_CHANGE",
            module="AUTH",
            title="Password Changed",
            description=f"{user.username} successfully changed their account password.",
            request=request,
        )

        return Response(
            {
                "message": "Password changed successfully! Please use your new password for future logins.",
                "success": True,
            },
            status=status.HTTP_200_OK,
        )


class ModuleView(ModelViewSet):
    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        school = self.request.user.school
        enabled_feature_ids = SchoolFeature.objects.filter(
            school=school,
            is_enabled=True,
            feature__is_active=True,
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






# ==========================================
# FORGOT PASSWORD WITH SMTP EMAIL & OTP
# ==========================================
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
import random

class ForgotPasswordSendOTPView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        if not email:
            return Response({"error": "Please provide an email address."}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Check if user exists with this email
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            staff = Staff.objects.filter(email__iexact=email).first()
            if staff and staff.user:
                user = staff.user
            else:
                student = Student.objects.filter(user__email__iexact=email).first()
                if student and student.user:
                    user = student.user
                else:
                    parent = Perents.objects.filter(user__email__iexact=email).first()
                    if parent and parent.user:
                        user = parent.user

        if not user:
            return Response(
                {"error": "No account found registered with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 2. Generate 6-digit OTP
        otp = str(random.randint(100000, 999999))

        # Clear existing OTPs for this email
        OTP.objects.filter(email__iexact=email).delete()

        # Save new OTP
        OTP.objects.create(email=email, otp=otp)

        # 3. Send email using SMTP
        display_name = user.first_name or user.username or "User"
        subject = f"{otp} is your verification code to reset your password"
        body = (
            f"Dear {display_name},\n\n"
            f"We received a request to reset your password for your School Management account.\n\n"
            f"Your 6-digit OTP verification code is:\n\n"
            f"    {otp}\n\n"
            f"This code will expire in 10 minutes.\n\n"
            f"If you did not request this password reset, please ignore this email or contact your school administrator.\n\n"
            f"Warm regards,\n"
            f"School Management Administration"
        )

        sent = False
        last_error = None

        # 1st attempt: Standard Django send_mail
        try:
            from django.conf import settings
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "yash.error.1@gmail.com")
            send_mail(
                subject=subject,
                message=body,
                from_email=from_email,
                recipient_list=[email],
                fail_silently=False,
            )
            sent = True
        except Exception as e:
            last_error = str(e)
            # 2nd attempt: Automatic fallback to Port 465 (Direct SSL)
            try:
                from django.conf import settings
                from django.core.mail import EmailMessage, get_connection
                ssl_conn = get_connection(
                    backend="django.core.mail.backends.smtp.EmailBackend",
                    host=getattr(settings, "EMAIL_HOST", "smtp.gmail.com"),
                    port=465,
                    username=getattr(settings, "EMAIL_HOST_USER", "yash.error.1@gmail.com"),
                    password=getattr(settings, "EMAIL_HOST_PASSWORD", ""),
                    use_ssl=True,
                    use_tls=False,
                    timeout=15,
                )
                fallback_msg = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "yash.error.1@gmail.com"),
                    to=[email],
                    connection=ssl_conn,
                )
                fallback_msg.send(fail_silently=False)
                sent = True
            except Exception as e2:
                last_error = f"{last_error} | SSL Fallback: {str(e2)}"

        if not sent:
            return Response(
                {
                    "error": f"Failed to send verification email via SMTP: {last_error}",
                    "help": "Please verify your Gmail App Password at myaccount.google.com/apppasswords and check if your local network or firewall allows outbound SMTP on port 465/587."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"message": "Verification code has been sent to your email successfully."},
            status=status.HTTP_200_OK,
        )


class ForgotPasswordResetView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        otp = (request.data.get("otp") or "").strip()
        new_password = (request.data.get("new_password") or "").strip()

        if not email or not otp or not new_password:
            return Response(
                {"error": "Email, OTP, and new password are all required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from .validators import validate_strong_password
            validate_strong_password(new_password)
        except Exception as ve:
            err_msg = ve.detail[0] if hasattr(ve, "detail") and isinstance(ve.detail, list) else str(ve)
            return Response(
                {"error": err_msg},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Verify OTP within 10 minutes
        ten_minutes_ago = timezone.now() - timedelta(minutes=10)
        otp_record = OTP.objects.filter(
            email__iexact=email,
            otp=otp,
            created_at__gte=ten_minutes_ago,
        ).order_by("-created_at").first()

        if not otp_record:
            return Response(
                {"error": "Invalid or expired OTP code. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Find user
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            staff = Staff.objects.filter(email__iexact=email).first()
            if staff and staff.user:
                user = staff.user
            else:
                student = Student.objects.filter(user__email__iexact=email).first()
                if student and student.user:
                    user = student.user
                else:
                    parent = Perents.objects.filter(user__email__iexact=email).first()
                    if parent and parent.user:
                        user = parent.user

        if not user:
            return Response(
                {"error": "User account could not be found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Reset password
        user.set_password(new_password)
        user.save()

        # Delete used OTP
        OTP.objects.filter(email__iexact=email).delete()

        return Response(
            {"message": "Your password has been reset successfully. Please log in with your new password."},
            status=status.HTTP_200_OK,
        )
