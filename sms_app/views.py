from django.shortcuts import redirect, render
from django.urls import reverse

from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Q
from .models import Homework, HomeworkSubmission, Student, Division
from django.db import models

from rest_framework.permissions import BasePermission
from .models import UserModuleAccess

from sms_app.razorpay_client import client
from rest_framework.views import APIView

from os import link
from urllib import request, response

from django.http import JsonResponse
from django.shortcuts import render
from requests import get
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from django.core.cache import cache
from django.db import transaction
from rest_framework.permissions import IsAuthenticated

from sms_app.models import *
from sms_app.serializer import *
from rest_framework.permissions import BasePermission, IsAuthenticated
import random
import string
from django.contrib.auth.models import Group

from django.conf import settings
from django.db import transaction

from rest_framework.views import APIView
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Q

from rest_framework_simplejwt.views import TokenObtainPairView

from django.contrib.auth import get_user_model

User = get_user_model()


from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from sms_app.models import DocumentFile

from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from sms_app.models import DocumentFile

import hmac
import hashlib
from rest_framework import status
from django.conf import settings

import hmac
import hashlib

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# from .serializers import DocumentS

from django.core.cache import cache
from rest_framework import generics

import pandas as pd
from datetime import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model

# from yourapp.models import Student, SchoolClass, School

User = get_user_model()

from django.http import JsonResponse


def health_check(request):
    return JsonResponse({"status": "ok"})


# Create your views here.
# set access and refresh token in cookie
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
def generate_school_code(name):
    school_name = name.split(" ")[0]
    digit = string.digits

    four_digit = "".join(random.choices(digit, k=4))
    school_code = school_name + four_digit

    if School.objects.filter(code=school_code).exists():
        return generate_school_code(name)

    return school_code


def generate_staff_username(name):
    Staff_name = name.split(" ")[0]
    digit = string.digits

    four_digit = "".join(random.choices(digit, k=4))
    Staff_username = Staff_name + four_digit

    if User.objects.filter(username=Staff_username).exists():
        return generate_staff_username(name)

    return Staff_username


# ======END CODE for GENERATE ID & CODE =====


def generate_username(email=None, mobile=None, otp=None):
    if email:
        base = email.split("@")[0][:4]  # first 4 chars
    else:
        base = mobile[-4:]  # last 4 digits of mobile

    otp_part = otp[-3:] if otp else str(random.randint(100, 999))

    username = f"{base}{otp_part}".lower()

    # Ensure uniqueness
    while User.objects.filter(username=username).exists():
        random_suffix = "".join(random.choices(string.digits, k=3))
        username = f"{base}{random_suffix}"

    return username


# ========= TO GENERATE OTP=========
def generate_otp():
    return str(random.randint(100000, 999999))


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

# from .serializers import SendOTPSerializer, VerifyOTPSerializer
from .models import OTP
import random
from django.core.mail import send_mail

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def send_otp_email(email, otp, user_name=None):
    subject = "Your OTP Code"

    html_content = render_to_string(
        "otp_email.html", {"otp": otp, "user_name": user_name}
    )

    email_message = EmailMultiAlternatives(
        subject=subject,
        body=f"Your OTP is {otp}",  # fallback (plain text)
        from_email="yash.error.1@gmail.com",
        to=[email],
    )

    email_message.attach_alternative(html_content, "text/html")
    email_message.send()


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


class LoginView(APIView):

    def post(self, request):

        # =====================================
        # Validate User
        # =====================================
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

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
        # WEB
        # Store Tokens in HttpOnly Cookies
        # =====================================
        response = Response(
            {
                "school_id": response_data["school_id"],
                "school_slug": response_data["school_slug"],
                "roles": response_data["roles"],
                "modules": response_data["modules"],
            },
            status=status.HTTP_200_OK,
        )

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="None",
            max_age=60 * 60,
            path="/",
        )

        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,
            samesite="None",
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


class Is_super_admin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="super_admin").exists()
        )


class Is_admin_trustee(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="admin(trustee)").exists()
        )


class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="CLERK").exists()
        )


class IsFeeManager(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="FEES MANAGEMENT").exists()
        )


class Isprincipal(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="PRINCIPAL").exists()
        )


class Isstudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="student").exists()
        )
        
class Isteacher(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="TEACHER").exists()
        )


class IsTempUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="temp_user").exists()
        )


class HasModuleAccess(BasePermission):
    """
    Allows access if user is mapped to module
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        if not user.is_active:
            return False

        if user.is_superuser:
            return True

        module_code = getattr(view, "module_code", None)

        if not module_code:
            raise AttributeError("module_code is required in the view")

        return UserModuleAccess.objects.filter(
            user=user, module__code=module_code, module__is_active=True
        ).exists()


class FeatureView(ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerialzer
    permission_classes = [IsAuthenticated, Is_super_admin]

    http_method_names = ["get", "post", "delete"]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"message": "Feature created successfully"}, status=201)


class SchoolFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = SchoolFeatureSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]


class GetFeatureView(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = GetFeatureSerializer
    permission_classes = [IsAuthenticated, Is_admin_trustee]

    http_method_names = ["get"]

    def get_queryset(self):
        school = self.request.user.school
        return SchoolFeature.objects.filter(school=school, is_enabled=True)


class ChangeFeatureStatusVIew(ModelViewSet):
    queryset = SchoolFeature.objects.all()
    serializer_class = ChangeFeatureStatusSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]
    http_method_names = ["patch"]
    lookup_field = "id"


from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from django.db import transaction
from django.core.cache import cache
from rest_framework import serializers


class SchoolView(ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    # ✅ Cache-safe queryset
    def get_queryset(self):
        # cache_key = "school_list"
        # data = cache.get(cache_key)

        qs = School.objects.all()
        # cache.set(cache_key, qs, timeout=300)
        return qs

    def perform_create(self, serializer):
        features = serializer.validated_data.pop("feature_ids", [])
        name = serializer.validated_data.get("name")
        email = serializer.validated_data.get("email")

        if not email:
            raise serializers.ValidationError("Provide email for school admin user")

        # ✅ Generate unique school code
        school_code = generate_school_code(name)
        while User.objects.filter(username=school_code).exists():
            school_code = generate_school_code(name)

        with transaction.atomic():
            # ✅ Create user
            user = User.objects.create(username=school_code, email=email)
            user.role = "admin(trustee)"  # if custom field exists
            user.set_password("123456")
            user.save()

            # ✅ Assign group
            group, _ = Group.objects.get_or_create(name="admin(trustee)")
            user.groups.add(group)

            # ✅ Create school
            school = serializer.save(login_id=user)

            # ✅ Bulk create school features
            school_features = [
                SchoolFeature(school=school, feature=feature, is_enabled=True)
                for feature in features
            ]

            SchoolFeature.objects.bulk_create(school_features)

            # ✅ Link user to school
            user.school = school  # if field exists
            user.save()
        #  Clear cache after create
        # cache.delete("school_list")

    # 🔹 Update + clear cache
    def perform_update(self, serializer):
        serializer.save()
        cache.delete("school_list")

    # 🔹 Delete + clear cache
    def perform_destroy(self, instance):
        instance.delete()
        cache.delete("school_list")

    # 🔹 Custom response
    def create(self, request, *args, **kwargs):
        super().create(request, *args, **kwargs)
        return Response({"message": "School created Successfully"}, status=201)


class ManualStudentView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = ManualStudentSerializer
    http_method_names = ["post"]

    def perform_create(self, serializer):

        return serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        return Response({"message": "Student Added Successfully"})


from rest_framework import generics


class SchoolListView(generics.ListAPIView):
    queryset = School.objects.all()
    serializer_class = SchoolListSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]


class RazarDataView(ModelViewSet):
    queryset = RazorPayData.objects.all()
    serializer_class = RazarDataSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]


class StaffView(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, Is_admin_trustee]

    # 🔹 Get staff list with Redis cache
    def get_queryset(self):
        user = self.request.user
        # cache_key = f"staff_list_{user.id}"

        # staff_qs = cache.get(cache_key)
        # if staff_qs:
        #     print("its form cach")

        # if not staff_qs:
        staff_qs = Staff.objects.filter(school__login_id=user)
        # cache.set(cache_key, staff_qs, timeout=60 * 60 * 5)  # 5 hours cache

        return staff_qs

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response(
            {"message": "Staff created successfully"}, status=status.HTTP_201_CREATED
        )

    # Create staff + clear cache
    def perform_create(self, serializer):
        name = serializer.validated_data.get("name")
        category = serializer.validated_data.pop("category")
        email = serializer.validated_data.get("email")
        mobile = serializer.validated_data.get("mobile")

        if not email and not mobile:
            raise serializers.ValidationError("Provide email or mobile for staff user")
        category = int(category)

        cat = Feature.objects.filter(id=category).first()

        group, created = Group.objects.get_or_create(name=cat.name)

        username = generate_staff_username(name)

        with transaction.atomic():
            user = User(username=username)
            user.school = self.request.user.school
            user.role = category
            user.email = email if email else None
            user.mobile = mobile if mobile else None

            user.set_password("123456")
            user.save()

            user.groups.add(group)
            print(category)

            modules = Module.objects.filter(for_role=category)

            print(modules)
            for m in modules:
                UserModuleAccess.objects.create(user=user, module=m)

            school = School.objects.filter(login_id=self.request.user).first()

        serializer.save(user=user, school=school, category=cat.name)

    def perform_update(self, serializer):
        serializer.save()
        cache.delete(f"staff_list_{self.request.user.id}")

    # 🔹 Delete staff + clear cache
    def perform_destroy(self, instance):
        instance.delete()
        cache.delete(f"staff_list_{self.request.user.id}")


class GetTeacherView(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = GetTeacherSerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    http_method_names = ["get"]

    def get_queryset(self):
        school = self.request.user.school
        return Staff.objects.filter(school=school, user__groups__name="TEACHER")


# =============TO ask more=========

# class FormViewSet(ModelViewSet):
#     queryset = Form.objects.all()
#     serializer_class = FormSerializer
#     # permission_classes = [IsAuthenticated]

# class FormDetailAPIView(RetrieveAPIView):
#     queryset = Form.objects.all()
#     serializer_class = FormSerializer


# class SubmitFormView(APIView):
#     def post(self, request, id):
#         print("RAW BODY:", request.body)
#         print("PARSED DATA:", request.data)

#         form = Form.objects.get(id=id)

#         for field in form.fields.all():
#             print("Looking for key:", str(field.id))

#             value = request.data.get(str(field.id))
#             print("VALUE FOUND:", value)

#             field.value = value
#             field.save()

#         return Response({"message": "Saved"})

# =============end TO ask more===========


# class StudentView(ModelViewSet):
#     queryset = Student.objects.all()
#     serializer_class = StudentSerializer

#     def perform_create(self, serializer):
#         student = serializer.save()

#     # Now safely access fields from the saved instance
#         link = f"http://127.0.0.1:8000/admission?id={student.id}"

#         send_mail(
#             subject="Admission Form",
#             message=f"Fill this admission form using the link: {link}",
#             from_email=settings.EMAIL_HOST_USER,
#             recipient_list=[student.email],
#         )


# class StudentDocumentview(ModelViewSet):
#     queryset = StudentDocument.objects.all()
#     serializer_class = StudentDocumentSerializer

#     def get_queryset(self):
#         queryset = super().get_queryset()
#         student_id = self.request.query_params.get('student_id')

#         if student_id:
#             queryset = queryset.filter(student_id=student_id)

#         return queryset


class TempUserAdmissionViewSet(ReadOnlyModelViewSet):
    serializer_class = TempUserAdmissionDataSerializer

    def get_queryset(self):
        return (
            Admission.objects.filter(temp_user=self.request.user)
            .select_related("school", "form")
            .prefetch_related("field_values__field__section")
        )


# ----------TO GET ADMISSION DATA TO TRUSTEE----------------


class AdmissionReadOnlyViewSet(ReadOnlyModelViewSet):
    serializer_class = GetAdmissionDataSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    # def get_queryset(self):
    #     user = self.request.user

    #     # Multi-tenant safety (VERY IMPORTANT for your SaaS)
    #     return Admission.objects.filter(fee_verified = True, school=user.school).prefetch_related(
    #         "field_values", "documents"
    #     )

    def get_queryset(self):
        verified_admission_ids = StudentVerify.objects.filter(
            clerk_verify=True
        ).values_list("admission_number", flat=True)
        user = self.request.user
        verified_admission_ids = list(verified_admission_ids)
        # print(verified_admission_ids)
        # verified_admission_ids = [1,2,"141357-jagr-ADM-0022","149928-jagr-ADM-0026"]

        return (
            Admission.objects.filter(fee_verified=True, school=user.school)
            .exclude(admission_number__in=verified_admission_ids)
            .prefetch_related("field_values", "documents")
        )


# ======================================================================


class ClerkVerifyView(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = ClerkVerifySerializer
    permission_classes = [IsAuthenticated, IsCLerk]
    lookup_field = "admission_number"
    http_method_names = ["patch"]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {"message": "Clerk updated successfully"}, status=status.HTTP_200_OK
        )


class PrincipleVerifyView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = PrincipleVerifySerializr

    def get_queryset(self):
        school = self.request.user.school
        return Student.objects.filter(clerk_verified=True, school=school)


# ======Fee Verify View =============


class FeeVerifyView(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = FeesVerifySerializer
    permission_classes = [IsAuthenticated, IsFeeManager]
    lookup_field = "admission_number"

    def get_queryset(self):
        return Admission.objects.filter(
            pay_process=True, school=self.request.user.school
        )

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                "message": "Fee verified successfully",
                "admission_number": response.data.get("admission_number"),
            },
            status=response.status_code,
        )


# ========================================


# =====serializer for School class=====
# this for only get its public use on Admission fprosecc
class ClassView(ModelViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get_queryset(self):
        school = self.request.user.school
        return SchoolClass.objects.filter(school=school)


from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from sms_app.models import SchoolClass

# from .serializers import SchoolClassSerializer


class SchoolClassView(ModelViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    permission_classes = [IsAuthenticated, Isprincipal]

    def get_queryset(self):
        #  only show classes of logged-in user's school
        return SchoolClass.objects.filter(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        #  accept multiple objects
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)

        # save with school
        serializer.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)


#     def list(self, request, *args, **kwargs):
#         school_id = request.user.school.id
#         cache_key = f"school_classes_{school_id}"

#         data = cache.get(cache_key)

#         if data:
#             print("cach")

#         if not data:
#             queryset = self.get_queryset()
#             serializer = self.get_serializer(queryset, many=True)
#             data = serializer.data

#             cache.set(cache_key, data, timeout=60*10)

#         return Response(data)

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)

#         instance = serializer.save()
#         cache.delete(f"school_classes_{instance.school.id}")

#     def perform_update(self, serializer):
#         instance = serializer.save()
#         cache.delete(f"school_classes_{instance.school.id}")

#     def perform_destroy(self, instance):
#         school_id = instance.school.id
#         instance.delete()
#         cache.delete(f"school_classes_{school_id}")

#     def create(self, request, *args, **kwargs):
#         super().create(request, *args, **kwargs)
#         return Response({
#             "message": "Class created Successfully"
#         }, status=201)
# # ========================================

# ========= admissions process views ========

# ========= using this serializers principle set DocumentField=========

# class DocumentFieldview(ModelViewSet):
#     queryset = DocumentField.objects.all()
#     serializer_class = DocumentFileSerializer

# =====================================================================


class AdmissionFormViewSet(ModelViewSet):
    queryset = AdmissionForm.objects.all()
    serializer_class = AdmissionFormSerializer
    permission_classes = [IsAuthenticated, Isprincipal]

    lookup_field = "unique_link"
    # access form via UUID

    # def get_serializer_class(self):
    #     return AdmissionFormSerializer

    def get_queryset(self):
        return AdmissionForm.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            instance = serializer.save()

        return Response(
            {
                "message": "Form created successfully",
            },
            status=status.HTTP_201_CREATED,
        )


# ====this view set for view admission form field====


class FormFieldViewSet(RetrieveAPIView):
    serializer_class = AdmissionFormViewSerializer
    permission_classes = [IsAuthenticated, IsTempUser]

    def get_queryset(self):

        school = self.request.user.school

        # Only active forms, read-only single record

        return AdmissionForm.objects.filter(school=school, is_active=True).first()

    def get_object(self):
        # Return only one active record (first one)
        return self.get_queryset()


# ===================================================
# for admission form status change
class FormStatus(ModelViewSet):
    queryset = AdmissionForm.objects.all()
    serializer_class = ChangeFormStatus
    permission_classes = [IsAuthenticated, Isprincipal]
    http_method_names = ["patch"]

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        is_active = request.data.get("is_active")

        with transaction.atomic():
            # If setting this form to active
            if is_active is True or is_active == "true":
                # Make all other forms inactive
                AdmissionForm.objects.exclude(id=instance.id).filter(
                    school=user.school
                ).update(is_active=False)

            # Update current instance
            serializer = self.get_serializer(instance, data=request.data, partial=True)

            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            {
                "message": "Form Public successfully",
                # "data": serializer.data
            },
            status=status.HTTP_200_OK,
        )


# for send form link


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ShareFormLink(request):
    form = AdmissionForm.objects.filter(
        school=request.user.school, is_active=True
    ).first()

    form_link = f"api/admission/{form.unique_link}/"

    return Response({"form_link": form_link})


FRONTEND_LOGIN_URL = "https://edunet-one.vercel.app/login"


class Admission_link(APIView):
    def get(self, request, unique_link):
        # Find form by unique_link
        form = AdmissionForm.objects.filter(unique_link=unique_link).first()

        # Invalid link
        if not form:
            return Response(
                {"message": "Invalid admission link"}, status=status.HTTP_404_NOT_FOUND
            )

        # Block if form is inactive
        if not form.is_active:
            return Response(
                {"message": "Admission form is closed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return school details
        return Response(
            {
                "school_id": form.school.id,  # use .id not object
                "school_slug": form.school.slug,
            },
            status=status.HTTP_200_OK,
        )


class FormSubmissionViewSet(ModelViewSet):
    queryset = Admission.objects.all()
    permission_classes = [IsTempUser]
    serializer_class = AdmissionSubmissionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # def get_serializer_class(self):
    #     if self.action in ['list', 'retrieve']:
    #         return FormSubmissionReadSerializer
    #     return FormSubmissionSerializer

    # def perform_create(self, serializer):
    #     serializer.save(user=self.request.user)


class DocumentSubmissionView(ModelViewSet):
    queryset = AdmissionDocument.objects.all()
    serializer_class = AdmissionDocumentSubmissionSerializer
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsTempUser]

    def create(self, request, *args, **kwargs):
        data = request.data  # .copy()

        documents = []
        i = 0

        while True:
            document_field = data.get(f"documents[{i}][document_field]")
            file = data.get(f"documents[{i}][file]")

            if not document_field and not file:
                break

            documents.append(
                {
                    "document_field": document_field,
                    "file": file,
                }
            )
            i += 1

        final_data = {
            "admission_number": data.get("admission_number"),
            "documents": documents,
        }

        serializer = self.get_serializer(data=final_data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(
            {
                "message": "Documents uploaded successfully",
                "admission_number": data.get("admission_number"),
            }
        )


# ==================UPDATE SUBMITED DATA BY CLERK===================
class AdmissionUpdateViewSet(ModelViewSet):
    queryset = Admission.objects.all()
    serializer_class = AdmissionUpdateSerializer
    lookup_field = "admission_number"
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def get_serializer_class(self):
        # if self.action in ["update", "partial_update"]:
        return AdmissionUpdateSerializer
        # return admissionViewSerializer

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response(
            {
                "message": "Admission updated successfully",
                "data": response.data,
            },
            status=response.status_code,
        )


# ==================================================================================
# class FormSubmissionReadView(ModelViewSet):
#     queryset = Student.objects.all()
#     serializer_class = FormSubmissionReadSerializer


#  =========update document by clerk after submission=====


class AdmissionDocumentViewSet(ModelViewSet):

    queryset = Admission.objects.all()

    lookup_field = "admission_number"

    permission_classes = [IsAuthenticated, IsCLerk]

    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Admission.objects.filter(school=self.request.user.school)

    def get_serializer_class(self):

        if self.action in ["update", "partial_update"]:
            return AdmissionDocumentUpdateSerializer

        return AdmissionDocumentUpdateSerializer

    def update(self, request, *args, **kwargs):

        partial = kwargs.pop("partial", False)

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        self.perform_update(serializer)

        return Response(
            {
                "message": "Admission documents updated successfully",
                "admission_number": instance.admission_number,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):

        kwargs["partial"] = True

        return self.update(request, *args, **kwargs)


# ======================================================


class CheckMobileAPIView(APIView):
    def post(self, request):
        serializer = MobileCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        mobile = serializer.validated_data["mobile"]

        student = Student.objects.filter(mobile=mobile).first()

        # CASE 1: Already used
        if student and student.details_done:
            return Response(
                {"status": "used", "message": "This number is already used"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        #  CASE 2: Resume
        if student and not student.details_done:
            values = StudentFieldValue.objects.filter(student=student)

            return Response(
                {
                    # "status": "resume",
                    "id": student.id,
                    "mobile": student.mobile,
                    "school": student.school.id if student.school else None,
                    "school_class": (
                        student.school_class.id if student.school_class else None
                    ),
                    "field_values": [
                        {"field": v.field.id, "value": v.value} for v in values
                    ],
                },
                status=status.HTTP_200_OK,
            )

        # CASE 3: New number
        return Response(
            {"status": "new", "message": "Mobile number is available"},
            status=status.HTTP_200_OK,
        )


import razorpay


class RazorpayOrderView(APIView):

    def post(self, request):

        amount = request.data.get("amount")
        admission_number = request.data.get("admission_number")

        # Validation
        if not amount:
            return Response(
                {"error": "Amount is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not admission_number:
            return Response(
                {"error": "Admission number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount) * 100
        except ValueError:
            return Response(
                {"error": "Invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Save temporary payment record
        with transaction.atomic():
            admission_fee = AdmissionFee.objects.create(
                amount=amount / 100,
                admission_number=admission_number,
            )

            admission = Admission.objects.filter(
                admission_number=admission_number
            ).first()
            admission.fee_amount = amount / 100
            admission.save()

        #   ============FOR INDIVIDUAL SCHOOL =============

        school = self.request.user.school

        razorpay_data = RazorPayData.objects.filter(school_id=school.id).first()

        if not razorpay_data:
            return Response(
                {"error": "Razorpay configuration not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create dynamic razorpay client
        client = razorpay.Client(
            auth=(
                razorpay_data.razorpay_key_id,
                razorpay_data.razorpay_secret_key,
            )
        )
        # ----------------------------------------------------
        # Create Razorpay Order

        razor_order = client.order.create(
            {
                "amount": amount,
                "currency": "INR",
                "payment_capture": 1,
            }
        )

        # Save order id
        admission_fee.razorpay_order_id = razor_order["id"]
        admission_fee.save()

        return Response(
            {
                "id": razor_order["id"],
                "key": settings.RAZOR_PAY_KEY_ID,  # "key": razorpay_data.razorpay_key_id, FOR INDIVIDUAL SCHOOL
                "amount": razor_order["amount"],
                "currency": "INR",
                "admission_number": admission_number,
            },
            status=status.HTTP_200_OK,
        )


from django.utils import timezone


# =======for online payment=========
class VerifyPaymentView(APIView):
    def post(self, request):
        data = request.data

        order_id = data.get("razorpay_order_id")
        payment_id = data.get("razorpay_payment_id")
        signature = data.get("razorpay_signature")

        admission_number = data.get("admission_number")

        # Convert to integer if it's a string
        # student = Student.objects.filter(id =student_id).first()

        # if student.details_done:
        #     return Response({"error": "Payment process are already done"}, status=400)

        # print("RAZORPAY_ORDER_ID", order_id)
        # print("RAZORPAY_PAYMENT_ID", payment_id)
        # print("RAZORPAY_SIGNATURE", signature)

        if not all([order_id, payment_id, signature]):
            return Response({"error": "Missing payment parameters"}, status=400)

        secret = settings.RAZOR_PAY_SECRET_KEY
        message = f"{order_id}|{payment_id}"

        generated_signature = hmac.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response({"status": "failed"}, status=400)

        try:
            payment = AdmissionFee.objects.get(razorpay_order_id=order_id)
        except AdmissionFee.DoesNotExist:
            return Response({"error": "Order not found"}, status=404)

        # form_data = AdmissionForm.objects.filter(id=form_id).first()
        # if not form_data:
        #     return Response({"error": "Form not found"}, status=404)

        # student = Student.objects.filter(id=student_id).first()
        # if not student:
        #     return Response({"error": "Student not found"}, status=404)

        # if student.details_done:
        #     return Response({"error": "Payment process are already done"}, status=404)

        with transaction.atomic():
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            # payment.student = student
            payment.school = request.user.school  # correct
            payment.payment_mode = "online"
            payment.paid_at = timezone.now()
            payment.save()
            admission = Admission.objects.filter(
                admission_number=admission_number
            ).first()
            admission.pay_process = True
            admission.save()
            # student.details_done = True
            # student.save()

        return Response({"status": "success"})


class OffilinePaymentView(APIView):

    def post(self, request):

        amount = request.data.get("amount")
        admission_number = request.data.get("admission_number")

        # Validation
        if not amount:
            return Response(
                {"error": "Amount is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not admission_number:
            return Response(
                {"error": "Admission number is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            amount = int(amount)
        except ValueError:
            return Response(
                {"error": "Invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check existing payment
        existing_payment = AdmissionFee.objects.filter(
            admission_number=admission_number,
            payment_mode="offline",
        ).first()

        if existing_payment:
            return Response(
                {"error": "Offline payment already completed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():

            payment = AdmissionFee.objects.create(
                amount=amount,
                admission_number=admission_number,
                school=request.user.school,
                payment_mode="offline",
                paid_at=timezone.now(),
            )

            admission = Admission.objects.filter(
                admission_number=admission_number
            ).first()
            admission.pay_process = True
            admission.save()

        return Response(
            {
                "status": "success",
                "payment_id": payment.id,
                "admission_number": admission_number,
                "payment_mode": "offline",
            },
            status=status.HTTP_200_OK,
        )


def get_receipt(request, student_id, form_id):

    student = Student.objects.filter(id=student_id).first()

    message = None
    field_values = None
    if student.details_done:
        field_values = StudentFieldValue.objects.select_related("field").filter(
            student_id=student_id, form_id=form_id
        )

    else:
        message = "Some Think error admission process are not done yet"
    # Example: Payment (if you have model)
    # payment = Payment.objects.filter(student_id=student_id).last()

    context = {
        "fields": field_values,
        # "payment": payment,
        "message": message,
    }

    return render(request, "receipt.html", context)


from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
from itertools import cycle


@method_decorator(csrf_exempt, name="dispatch")
class RazorpayWebhookView(APIView):
    def post(self, request):
        payload = request.body
        signature = request.headers.get("X-Razorpay-Signature")

        secret = settings.RAZOR_PAY_SECRET_KEY

        generated_signature = hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()

        if generated_signature == signature:
            data = json.loads(payload)

            if data["event"] == "payment.captured":
                payment_data = data["payload"]["payment"]["entity"]

                order_id = payment_data["order_id"]

                try:
                    payment = AdmissionFee.objects.get(razorpay_order_id=order_id)
                    payment.status = "paid"
                    payment.save()
                except AdmissionFee.DoesNotExist:
                    pass

            return Response({"status": "ok"})

        return Response({"status": "invalid"}, status=400)


# NOT IN USE
class DivisionSetView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = DivisionSetSerilaizer


# Only for Post method  from rest_framework.response import Response
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from django.core.cache import cache
import string

from django.core.cache import cache
import string


class SetDivisionView(ModelViewSet):
    queryset = Division.objects.all()
    serializer_class = SetDivisionSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    # ✅ GET (LIST with safe cache)
    def list(self, request, *args, **kwargs):
        school_id = request.user.school.id
        cache_key = f"divisions_school_{school_id}"

        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(
                    {"message": "Data fetched from cache", "data": cached_data}
                )
        except Exception:
            pass  # Ignore Redis error

        queryset = Division.objects.filter(school_id=school_id)
        serializer = self.get_serializer(queryset, many=True)

        try:
            cache.set(cache_key, serializer.data, timeout=60 * 10)
        except Exception:
            pass  # Ignore Redis error

        return Response(serializer.data)

    # CREATE
    def create(self, request, *args, **kwargs):
        division_count = request.data.get("division")
        school_class = request.data.get("SchoolClass")
        capacity = request.data.get("capacity")

        if not division_count:
            return Response({"error": "division is required"}, status=400)

        if not school_class:
            return Response({"error": "SchoolClass is required"}, status=400)

        if not capacity:
            return Response({"error": "capacity is required"}, status=400)

        try:
            division_count = int(division_count)
            capacity = int(capacity)
        except ValueError:
            return Response(
                {"error": "division and capacity must be integers"}, status=400
            )

        if division_count <= 0 or division_count > 26:
            return Response({"error": "division must be between 1 and 26"}, status=400)

        existing = Division.objects.filter(SchoolClass_id=school_class).count()
        if existing > 0:
            return Response(
                {"error": "Divisions already exist for this class"}, status=400
            )

        alphabet = list(string.ascii_uppercase[:division_count])

        divisions = []
        for a in alphabet:
            obj = Division.objects.create(
                SchoolClass_id=school_class,
                division=a,
                school=self.request.user.school,
                capacity=capacity,
            )
            divisions.append(obj)

        #  Clear Cache (SAFE)
        try:
            cache.delete(f"divisions_school_{request.user.school.id}")
        except Exception:
            pass

        serializer = self.get_serializer(divisions, many=True)

        return Response(
            {"message": "Division created Successfully", "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    #  UPDATE (SAFE cache clear)
    def perform_update(self, serializer):
        instance = serializer.save()

        try:
            cache.delete(f"divisions_school_{instance.school.id}")
        except Exception:
            pass

    #  DELETE (SAFE cache clear)
    def perform_destroy(self, instance):
        try:
            cache.delete(f"divisions_school_{instance.school.id}")
        except Exception:
            pass

        instance.delete()


# This Logic perfom with button after admission and complete and division is set
@transaction.atomic
def assign_student_divisions():
    # Get all classes
    classes = SchoolClass.objects.all()

    for school_class in classes:
        # Get divisions for this class
        divisions = list(
            Division.objects.filter(school_class=school_class).order_by("id")
        )

        # Skip if no divisions exist
        if not divisions:
            print(f"Skipping {school_class} (no divisions found)")
            continue

        division_len = len(divisions)

        # Get students of this class
        students = list(
            Student.objects.filter(school_class=school_class).order_by("created_at")
        )

        if not students:
            print(f"No students in {school_class}")
            continue

        # Optional: shuffle students for random distribution
        # random.shuffle(students)

        # Assign divisions (round-robin)
        for index, student in enumerate(students):
            student.division = divisions[index % division_len]

        # Bulk update for performance
        Student.objects.bulk_update(students, ["division"])



# ==================================================================



class ListDivisionView(ModelViewSet):
    queryset = Division.objects.all()
    serializer_class = SetDivisionSerializer
    permission_classes = [IsAuthenticated,Isteacher]
    http_method_names = ["get"]

    # ✅ GET (LIST with safe cache)
    def list(self, request, *args, **kwargs):
        school_id = request.user.school.id
        cache_key = f"divisions_school_{school_id}"

        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(
                    {"message": "Data fetched from cache", "data": cached_data}
                )
        except Exception:
            pass  # Ignore Redis error

        queryset = Division.objects.filter(school_id=school_id)
        serializer = self.get_serializer(queryset, many=True)

        try:
            cache.set(cache_key, serializer.data, timeout=60 * 10)
        except Exception:
            pass  # Ignore Redis error

        return Response(serializer.data)

from django.core.cache import cache
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache


class SetSubjectView(ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SetSubjectSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school)

    # ✅ CREATE
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save(school=request.user.school)

        school_id = request.user.school.id
        # school_class = instance.SchoolClass_id

        try:
            cache.delete(f"subjects_{school_id}_all")
            # cache.delete(f"subjects_{school_id}_{school_class}")
        except Exception:
            pass

        return Response(
            {
                "message": "Subject created successfully",
            },
            status=status.HTTP_201_CREATED,
        )

    # ✅ LIST
    def list(self, request, *args, **kwargs):
        school_id = request.user.school.id
        school_class = request.query_params.get("SchoolClass")

        cache_key = f"subjects_{school_id}_{school_class if school_class else 'all'}"

        # 🔐 SAFE CACHE GET
        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(
                    {"message": "Data fetched from cache", "data": cached_data}
                )
        except Exception:
            pass

        queryset = self.get_queryset()

        if school_class:
            queryset = queryset.filter(SchoolClass_id=school_class)

        serializer = self.get_serializer(queryset, many=True)

        # 🔐 SAFE CACHE SET
        try:
            cache.set(cache_key, serializer.data, timeout=60 * 10)
        except Exception:
            pass

        return Response({"message": "Data fetched from DB", "data": serializer.data})

    # ✅ RETRIEVE
    def retrieve(self, request, *args, **kwargs):
        subject_id = kwargs.get("pk")
        cache_key = f"subject_{subject_id}"

        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                return Response(
                    {"message": "Data fetched from cache", "data": cached_data}
                )
        except Exception:
            pass

        instance = self.get_object()
        serializer = self.get_serializer(instance)

        try:
            cache.set(cache_key, serializer.data, timeout=60 * 10)
        except Exception:
            pass

        return Response({"message": "Data fetched from DB", "data": serializer.data})

    # UPDATE
    def perform_update(self, serializer):
        instance = serializer.save()

        school_id = instance.school.id
        # school_class = instance.SchoolClass_id

        try:
            cache.delete(f"subjects_{school_id}_all")
            # cache.delete(f"subjects_{school_id}_{school_class}")
            cache.delete(f"subject_{instance.id}")
        except Exception:
            pass

    # DELETE
    def perform_destroy(self, instance):
        school_id = instance.school.id

        try:
            cache.delete(f"subjects_{school_id}_all")

            cache.delete(f"subject_{instance.id}")
        except Exception:
            pass

        instance.delete()


from django.core.cache import cache
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status


class SyllabusView(ModelViewSet):
    queryset = Syllabus.objects.all()
    serializer_class = SyllabusSerializer

    # ✅ Restrict to user's school
    def get_queryset(self):
        return Syllabus.objects.filter(school=self.request.user.school)

    # ✅ CREATE
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save(school=request.user.school)

        school_id = request.user.school.id
        # school_class = instance.SchoolClass_id

        # ✅ Clear cache
        # cache.delete(f"syllabus_{school_id}_all")
        # cache.delete(f"syllabus_{school_id}_{school_class}")

        return Response(
            {"message": "Syllabus created successfully", "data": serializer.data},
            status=status.HTTP_201_CREATED,
        )

    # ✅ LIST (WITH CACHE)
    def list(self, request, *args, **kwargs):
        school_id = request.user.school.id
        school_class = request.query_params.get("SchoolClass")

        cache_key = f"syllabus_{school_id}_{school_class if school_class else 'all'}"

        # ✅ Check cache
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response({"message": "Data fetched from cache", "data": cached_data})

        queryset = self.get_queryset()

        if school_class:
            queryset = queryset.filter(SchoolClass_id=school_class)

        serializer = self.get_serializer(queryset, many=True)

        # ✅ Store cache
        cache.set(cache_key, serializer.data, timeout=60 * 10)

        return Response({"message": "Data fetched from DB", "data": serializer.data})

    # ✅ RETRIEVE
    def retrieve(self, request, *args, **kwargs):
        syllabus_id = kwargs.get("pk")
        cache_key = f"syllabus_single_{syllabus_id}"

        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(
                {
                    "message": "Data fetched from cache",
                    # "data": cached_data
                }
            )

        instance = self.get_object()
        serializer = self.get_serializer(instance)

        cache.set(cache_key, serializer.data, timeout=60 * 10)

        return Response({"message": "Data fetched from DB", "data": serializer.data})

    # ✅ UPDATE
    def perform_update(self, serializer):
        instance = serializer.save()

        school_id = instance.school.id
        school_class = instance.id

        cache.delete(f"syllabus_{school_id}_all")
        cache.delete(f"syllabus_{school_id}_{school_class}")
        cache.delete(f"syllabus_single_{instance.id}")

    # ✅ DELETE
    def perform_destroy(self, instance):
        school_id = instance.school.id
        school_class = instance.id

        cache.delete(f"syllabus_{school_id}_all")
        cache.delete(f"syllabus_{school_id}_{school_class}")
        cache.delete(f"syllabus_single_{instance.id}")

        instance.delete()


class AssignClassView(ModelViewSet):
    queryset = AssignClass.objects.all()
    serializer_class = AssignClassSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):

        return AssignClass.objects.filter(school=self.request.user.school)


# ========= TIME TABLE VIEWs============


class Tt_yearView(ModelViewSet):
    queryset = Tt_year.objects.all()
    serializer_class = Tt_yearSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        school = self.request.user.school
        return Tt_year.objects.filter(school=school)


class Time_tableView(ModelViewSet):
    queryset = Tt_year.objects.all()
    serializer_class = Time_tableSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        school = self.request.user.school
        return Tt_year.objects.filter(school=school)


# class Tt_dayView(ModelViewSet):
#     queryset = Tt_day.objects.all()

#     serializer_class = Tt_daySerializer


class Tt_day_timeView(ModelViewSet):
    queryset = Tt_day_time.objects.all()
    serializer_class = Tt_day_timeSerializer


@api_view(["POST"])
def SetSlotView(request):
    class_div_id = request.data.get("class_div")
    school = getattr(request.user, "school", None)

    if not class_div_id:
        return Response(
            {"error": "class_div is required"}, status=status.HTTP_400_BAD_REQUEST
        )

    tt_days = Tt_day.objects.filter(class_div=class_div_id).select_related(
        "year", "class_div", "class_div__SchoolClass"
    )

    # if school:
    #     tt_days = tt_days.filter(school=school)

    if not tt_days.exists():
        return Response(
            {"error": "No timetable day found for the selected filters"},
            status=status.HTTP_404_NOT_FOUND,
        )

    assignments = list(
        AssignClass.objects.filter(division=class_div_id)
        .exclude(teacher__isnull=True)
        .select_related("teacher", "division")
    )

    print(class_div_id)
    print(assignments)
    # if school:
    #     assignments = [a for a in assignments if a.school_id == school.id]

    if not assignments:
        return Response(
            {"error": "No assigned teachers found for this class division"},
            status=status.HTTP_404_NOT_FOUND,
        )

    class_teacher_assignment = next(
        (item for item in assignments if item.is_class_teacher), None
    )
    other_assignments = [item for item in assignments if not item.is_class_teacher]
    random.shuffle(other_assignments)

    teacher_pool = other_assignments[:]
    if not teacher_pool and class_teacher_assignment:
        teacher_pool = [class_teacher_assignment]

    if not teacher_pool and not class_teacher_assignment:
        return Response(
            {"error": "No teachers available to set timetable"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    created_rows = []

    with transaction.atomic():
        for tt_day in tt_days:
            day_time = tt_day.tt_day_time_set.first()
            slots = list(tt_day.tt_slot_set.all().order_by("id"))

            if not day_time:
                return Response(
                    {"error": f"Day time is missing for {tt_day.day}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not slots:
                return Response(
                    {"error": f"Slots are missing for {tt_day.day}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            rotating_teachers = cycle(teacher_pool)

            for index, slot_obj in enumerate(slots):
                slot_data = slot_obj.slot or {}
                slot_label = str(slot_data.get("slot") or slot_obj.lecture)
                start_time = slot_data.get("start") or day_time.start
                end_time = slot_data.get("end") or day_time.end

                if index == 0 and class_teacher_assignment:
                    teacher = class_teacher_assignment.teacher
                else:
                    teacher = next(rotating_teachers).teacher

                timetable_obj, _ = Time_table.objects.update_or_create(
                    year=tt_day.year,
                    day=tt_day.day,
                    class_div=tt_day.class_div,
                    slot=slot_label,
                    defaults={
                        "school": school or tt_day.school,
                        "teacher": teacher,
                        "start": start_time,
                        "end": end_time,
                    },
                )
                created_rows.append(timetable_obj)

    serializer = SetTimeTableSerializer(created_rows, many=True)
    return Response(
        {
            "message": "Time table set successfully",
            "data": serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


# for get student for principle with filter     [school filter add remainig]
class GetStudentView(ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = GetStudentSerializer
    # permission_classes = [IsAuthenticated, Isprincipal]

    def get_queryset(self):
        # school = self.request.user.school or None
        queryset = Student.objects.filter(details_done=True)

        school_class = self.request.query_params.get("school_class")

        if school_class:
            queryset = queryset.filter(school_class=school_class)

        return queryset


class GetLocationView(APIView):
    permission_classes = [IsAuthenticated, IsCLerk]

    def post(self, request):
        serializer = AttendanceLocationSerializer(
            data=request.data, context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Location created successfully"},
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        queryset = AttendanceLocation.objects.filter(school=request.user.school)

        serializer = AttendanceLocationSerializer(
            queryset, many=True, context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)


class AttendanceView(ModelViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        return Response(
            {"message": "Attendance Added successfully", "data": response.data},
            status=status.HTTP_201_CREATED,
        )


class TodayAttendanceStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print("USER", user)
        staff = Staff.objects.filter(user=request.user).first()
        today = timezone.localdate()
        print(staff)

        if not staff:
            return Response(
                {"message": "Staff profile not found for current user."},
                status=status.HTTP_404_NOT_FOUND,
            )

        attendance = Attendance.objects.filter(
            staff=staff,
            attendance_date=today,
        ).first()

        if not attendance:
            return Response(
                {
                    "attendance_date": today,
                    "checked_in": False,
                    "checked_out": False,
                    "check_in": None,
                    "check_out": None,
                    "is_present": False,
                    "is_half_day": False,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "attendance_date": attendance.attendance_date,
                "checked_in": bool(attendance.check_in),
                "checked_out": bool(attendance.check_out),
                "check_in": attendance.check_in,
                "check_out": attendance.check_out,
                "is_present": attendance.is_present,
                "is_half_day": attendance.is_half_day,
            },
            status=status.HTTP_200_OK,
        )


class LeaveTemplateView(ModelViewSet):
    queryset = LeaveTemplate.objects.all()
    serializer_class = LeaveTemplateSerializer
    # permission_classes = [IsAuthenticated]

    def get_parsers(self):

        return super().get_parsers()


class LeaveRequestView(ModelViewSet):
    queryset = LeaveRequest.objects.all()
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]


class GetLeaveRequestView(ModelViewSet):
    queryset = LeaveRequest.objects.all()
    serializer_class = GetLeaveRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get"]

    def get_queryset(self):

        queryset = LeaveRequest.objects.filter(school=self.request.user.school)

        return queryset


class ChangeLeaveView(ModelViewSet):
    queryset = LeavePerDay.objects.all()
    serializer_class = ChangeLeavePerDaySerializer
    permission_classes = [IsAuthenticated, Isprincipal]
    http_method_names = ["patch"]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.leave.school != request.user.school:
            return Response(
                {"error": "You are not allowed to modify this record"}, status=403
            )

        return super().update(request, *args, **kwargs)


class GetRemainingLeaveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        leave_template = request.data.get("leave_template")
        user = request.user

        staff = Staff.objects.filter(user=user).first()
        queryset = StaffRemainingLeave.objects.filter(
            staff=staff, school=user.school, leave_template=leave_template
        )

        serializer = StaffRemainingLeaveSerializer(queryset, many=True)
        return Response(serializer.data)


class AnnouncementView(ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAuthenticated, Isprincipal]


class GetAnnouncementView(ModelViewSet):
    queryset = Announcement.objects.all()
    serializer_class = GetAnnouncementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        now = timezone.now()

        print(user.id)
        print(type(user.id))
        # Base filter (active announcements)
        base_filter = Q(school=user.school, publish_at__lte=now) & (
            Q(expires_at__gte=now) | Q(expires_at__isnull=True)
        )

        # ALL users
        # all_filter = Q(targets__target_type='ALL')

        # SPECIFIC user
        specific_filter = Q(targets__target_type="SPECIFIC", targets__target_id=user.id)

        # ROLE-based
        user_groups = user.groups.values_list("id", flat=True)
        print(user_groups)
        role_filter = Q(targets__target_type="ROLE", targets__target_id__in=user_groups)

        # 4️ CLASS-based (only if student)
        class_filter = Q()
        if hasattr(user, "student"):
            class_filter = Q(
                targets__target_type="CLASS",
                targets__target_id=user.student.school_class_id,
            )

        # Combine everything
        queryset = Announcement.objects.filter(specific_filter | base_filter).order_by(
            "-created_at"
        )

        return queryset

    # def school_wise_report(request, school_id):
    #     # Example: Get all students in the school
    #     # school = School.objects.filter(name=school_id)
    #     if school_id == 1:
    #         school = "madhuram"
    #     elif school_id == 2:
    #         school = "saraswati"

    #     # Example: Get all announcements for the school

    #     # Build your report data

    #     return render(request,"map.html", context={'school': school})


import pandas as pd
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# from yourapp.models import Student, SchoolClass, School
# from yourapp.permissions import IsCLerk


# ----------------------------
# Helpers
# ----------------------------


def parse_date(value):
    try:
        return pd.to_datetime(value).date() if pd.notna(value) else None
    except Exception:
        return None


def clean(value):
    return value if pd.notna(value) else None


# ----------------------------
# Column Mapping (Excel → Model)
# ----------------------------
COLUMN_MAPPING = {
    "GR No": "gr_no",
    "Surname": "surname",
    "Student Name": "name",
    "Father's Name": "father_name",
    "Mother's Name": "mother_name",
    "Aadhaar Card No": "aadhar_number",
    "Religion": "religion",
    "Caste Category": "scheduled_caste",
    "Place of Birth": "place_of_birth",
    "Date of Birth": "date_of_birth",
    "Admission Date": "admission_date",
    "Leaving Date": "leaving_date",
    "Last School Attended": "last_school",
    "Progress": "progress",
    "Conduct": "conduct",
    "Remarks": "remarks",
    "Mobile": "mobile",
    "Standard": "school_class",
    "Academic Year": "academic_year",
}


# ----------------------------
# Main Import Function
# ----------------------------


@transaction.atomic
def import_students_from_excel(file, school_id, use_bulk=True):
    df = pd.read_excel(file)
    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    school = School.objects.get(id=school_id)

    students = []
    errors = []

    # ✅ Track duplicates inside Excel
    excel_gr_set = set()

    # ✅ Fetch existing GR numbers from DB
    existing_gr_nos = set(
        Student.objects.filter(school=school).values_list("gr_no", flat=True)
    )

    for index, row in df.iterrows():
        try:
            data = {}
            for excel_col, model_field in COLUMN_MAPPING.items():
                data[model_field] = clean(row.get(excel_col))

            gr_no = str(data.get("gr_no")).strip() if data.get("gr_no") else None

            # ----------------------------
            # 🔴 GR NO VALIDATION
            # ----------------------------
            if not gr_no:
                errors.append(f"Row {index+2}: GR No is required")
                continue

            if gr_no in excel_gr_set:
                errors.append(f"Row {index+2}: Duplicate GR No '{gr_no}' in Excel")
                continue

            if gr_no in existing_gr_nos:
                errors.append(
                    f"Row {index+2}: GR No '{gr_no}' already exists for this school"
                )
                continue

            excel_gr_set.add(gr_no)

            # ----------------------------
            # Class validation
            # ----------------------------
            school_class = None

            if data.get("school_class"):
                class_name = str(data["school_class"]).strip()

                school_class = SchoolClass.objects.filter(
                    school_class=class_name,
                    school=school,
                ).first()

                if not school_class:
                    errors.append(f"Row {index+2}: Class '{class_name}' not found")
                    continue

            student_data = {
                "school": school,
                "gr_no": gr_no,
                "surname": data["surname"],
                "name": data["name"],
                "father_name": data["father_name"],
                "mother_name": data["mother_name"],
                "date_of_birth": parse_date(data["date_of_birth"]),
                "admission_date": parse_date(data["admission_date"]),
                "school_class": school_class,
                "academic_year": data["academic_year"],
                "mobile": data["mobile"],
                "aadhar_number": data["aadhar_number"],
            }

            extra_data = {
                "religion": data.get("religion"),
                "scheduled_caste": data.get("scheduled_caste"),
                "place_of_birth": data.get("place_of_birth"),
                "leaving_date": parse_date(data.get("leaving_date")),
                "last_school": data.get("last_school"),
                "progress": data.get("progress"),
                "conduct": data.get("conduct"),
                "remarks": data.get("remarks"),
            }

            students.append((student_data, extra_data))

        except Exception as e:
            errors.append(f"Row {index+2}: {str(e)}")

    # ----------------------------
    # STOP if any error
    # ----------------------------
    if errors:
        # rollback automatically due to atomic
        return {"created": 0, "errors": errors}

    # ----------------------------
    # Save to DB
    # ----------------------------
    created_count = 0

    if use_bulk:
        student_objects = [Student(**student_data) for student_data, _ in students]
        Student.objects.bulk_create(student_objects)

        created_students = Student.objects.filter(
            school=school,
            gr_no__in=[student_data["gr_no"] for student_data, _ in students],
        )
        student_map = {student.gr_no: student for student in created_students}

        extra_objects = []
        for student_data, extra_data in students:
            student = student_map.get(student_data["gr_no"])
            if student and any(extra_data.values()):
                extra_objects.append(StudentExtraData(student=student, **extra_data))

        if extra_objects:
            StudentExtraData.objects.bulk_create(extra_objects)

        created_count = len(student_objects)
    else:
        for student_data, extra_data in students:
            student = Student.objects.create(**student_data)
            if any(extra_data.values()):
                StudentExtraData.objects.create(student=student, **extra_data)
            created_count += 1

    return {"created": created_count, "errors": []}


# ----------------------------
# API View
# ----------------------------


class upload_students(APIView):
    permission_classes = [IsAuthenticated, IsCLerk]

    def post(self, request):
        if "file" not in request.FILES:
            return Response({"error": "No file uploaded"}, status=400)

        excel_file = request.FILES["file"]

        result = import_students_from_excel(
            file=excel_file,
            school_id=request.user.school.id,
            use_bulk=True,  # change to False for debugging
        )

        return Response(
            {
                "message": "Upload completed",
                "created": result["created"],
                "errors": result["errors"],
            }
        )


# ============FEE MANAGEMENT VIEW==============


class AcademicYearViewSet(ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class FeeTypeViewSet(ModelViewSet):
    queryset = FeeType.objects.all()
    serializer_class = FeeTypeSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        return FeeType.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        school = self.request.user.school
        serializer.save(school=school)


class FeeWiseClassViewSet(ModelViewSet):
    queryset = FeeWiseClass.objects.all()
    serializer_class = FeeWiseClassSerializer
    permission_classes = [IsAuthenticated, IsCLerk]

    def get_queryset(self):
        queryset = FeeWiseClass.objects.filter(
            school=self.request.user.school
        ).select_related("feetype", "school_class")

        feetype = self.request.query_params.get("feetype")
        school_class = self.request.query_params.get("school_class")

        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if school_class:
            queryset = queryset.filter(school_class_id=school_class)

        return queryset

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class SalaryComponentViewSet(ModelViewSet):
    queryset = SalaryComponent.objects.all()
    serializer_class = SalaryComponentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = SalaryComponent.objects.filter(school=self.request.user.school)

        component_type = self.request.query_params.get("component_type")
        is_active = self.request.query_params.get("is_active")

        if component_type:
            queryset = queryset.filter(component_type=component_type)
        if is_active in ["true", "false"]:
            queryset = queryset.filter(is_active=is_active == "true")

        return queryset.order_by("name")

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)
        
    def destroy(self, request, *args, **kwargs):
        response =  super().destroy(request, *args, **kwargs)
        
        return Response({
            "message":"Salary Component Deleted Successfully"
        })
    
    def update(self, request, *args, **kwargs):
        response =  super().update(request, *args, **kwargs)

        return Response({
            "message":"Salary Component Update Successfully"
        })

class StaffSalaryComponentViewSet(ModelViewSet):
    queryset = StaffSalaryComponent.objects.all()
    serializer_class = StaffSalaryComponentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = StaffSalaryComponent.objects.filter(
            staff__school=self.request.user.school
        ).select_related("staff", "component")

        staff = self.request.query_params.get("staff")
        component_type = self.request.query_params.get("component_type")
        is_active = self.request.query_params.get("is_active")

        if staff:
            queryset = queryset.filter(staff_id=staff)
        if component_type:
            queryset = queryset.filter(component__component_type=component_type)
        if is_active in ["true", "false"]:
            queryset = queryset.filter(is_active=is_active == "true")

        return queryset.order_by("staff__name", "component__name")
    
    def create(self, request, *args, **kwargs):
        response =  super().create(request, *args, **kwargs)
        
        staff = Staff.objects.filter(id = response.data.get("staff")).first()
        return Response({
            "message":"Salary Component Created Successfully",
            "staff":staff.name,
            "component_type":response.data.get("component_type")
        })

class StaffSalaryPaymentViewSet(ModelViewSet):
    queryset = StaffSalaryPayment.objects.all()
    serializer_class = StaffSalaryPaymentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_serializer_class(self):
        if self.action == "create":
            return GenerateStaffSalaryPaymentSerializer
        return StaffSalaryPaymentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save()
        response_serializer = StaffSalaryPaymentSerializer(
            payment, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        queryset = StaffSalaryPayment.objects.filter(
            school=self.request.user.school
        ).select_related("staff", "paid_by")

        staff = self.request.query_params.get("staff")
        salary_month = self.request.query_params.get("salary_month")
        payment_mode = self.request.query_params.get("payment_mode")
        payment_status = self.request.query_params.get("payment_status")

        if staff:
            queryset = queryset.filter(staff_id=staff)
        if salary_month:
            queryset = queryset.filter(salary_month=salary_month)
        if payment_mode:
            queryset = queryset.filter(payment_mode=payment_mode)
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)

        return queryset.order_by("-salary_month", "staff__name")


class StudentFeeViewSet(ModelViewSet):
    queryset = StudentFee.objects.all()
    serializer_class = StudentFeeSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = (
            StudentFee.objects.filter(school=self.request.user.school)
            .select_related(
                "academic_year",
                "student",
                "student__school_class",
                "feetype",
                "fee_wise_class",
            )
            .prefetch_related("payments")
        )

        student = self.request.query_params.get("student")
        school_class = self.request.query_params.get("school_class")
        academic_year = self.request.query_params.get("academic_year")
        feetype = self.request.query_params.get("feetype")
        status_value = self.request.query_params.get("status")
        billing_period = self.request.query_params.get("billing_period")

        if student:
            queryset = queryset.filter(student_id=student)
        if school_class:
            queryset = queryset.filter(student__school_class_id=school_class)
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if billing_period is not None:
            queryset = queryset.filter(billing_period=billing_period)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class MyStudentFeeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        student = Student.objects.filter(user=request.user).first()

        if not student:
            return Response(
                {"error": "Student profile not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = (
            StudentFee.objects.filter(student=student)
            .select_related(
                "academic_year",
                "student",
                "student__school_class",
                "feetype",
                "fee_wise_class",
            )
            .prefetch_related("payments")
        )

        status_value = request.query_params.get("status")
        academic_year = request.query_params.get("academic_year")
        billing_period = request.query_params.get("billing_period")

        if status_value:
            queryset = queryset.filter(status=status_value)
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)
        if billing_period is not None:
            queryset = queryset.filter(billing_period=billing_period)

        student_fees = list(queryset.order_by("-created_at"))
        for student_fee in student_fees:
            student_fee.apply_late_fee()

        serializer = StudentFeeSerializer(
            student_fees,
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)


class StudentFeePaymentViewSet(ModelViewSet):
    queryset = StudentFeePayment.objects.all()
    serializer_class = StudentFeePaymentSerializer
    permission_classes = [IsAuthenticated, IsFeeManager]

    def get_queryset(self):
        queryset = StudentFeePayment.objects.filter(
            school=self.request.user.school
        ).select_related(
            "student_fee",
            "student",
            "student__school_class",
            "feetype",
            "collected_by",
            "verified_by",
        )

        student_fee = self.request.query_params.get("student_fee")
        student = self.request.query_params.get("student")
        school_class = self.request.query_params.get("school_class")
        feetype = self.request.query_params.get("feetype")
        payment_mode = self.request.query_params.get("payment_mode")
        is_verified = self.request.query_params.get("is_verified")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")

        if student_fee:
            queryset = queryset.filter(student_fee_id=student_fee)
        if student:
            queryset = queryset.filter(student_id=student)
        if school_class:
            queryset = queryset.filter(student__school_class_id=school_class)
        if feetype:
            queryset = queryset.filter(feetype_id=feetype)
        if payment_mode:
            queryset = queryset.filter(payment_mode=payment_mode)
        if is_verified in ["true", "false"]:
            queryset = queryset.filter(is_verified=is_verified == "true")
        if date_from:
            queryset = queryset.filter(payment_date__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(payment_date__date__lte=date_to)

        return queryset.order_by("-payment_date", "-created_at")

    def perform_destroy(self, instance):
        student_fee = instance.student_fee
        instance.delete()
        student_fee.refresh_payment_status()


def get_student_fee_for_online_payment(user, student_fee_id):
    student = Student.objects.filter(user=user).select_related("school").first()

    if student:
        student_fee = StudentFee.objects.select_related(
            "student", "feetype", "school"
        ).get(id=student_fee_id, student=student, school=student.school)
        return student_fee, student.school

    school = getattr(user, "school", None)
    if not school:
        raise StudentFee.DoesNotExist

    student_fee = StudentFee.objects.select_related("student", "feetype", "school").get(
        id=student_fee_id, school=school
    )
    return student_fee, school


def get_student_fee_payment_for_online_verify(user, order_id):
    student = Student.objects.filter(user=user).select_related("school").first()
    queryset = StudentFeePayment.objects.select_related(
        "student_fee",
        "student_fee__student",
        "student_fee__feetype",
        "student",
        "feetype",
    ).filter(razorpay_order_id=order_id)

    if student:
        return queryset.get(student=student, school=student.school)

    school = getattr(user, "school", None)
    if not school:
        raise StudentFeePayment.DoesNotExist

    return queryset.get(school=school)


class StudentFeeRazorpayOrderView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student_fee_id = request.data.get("student_fee")
        requested_amount = request.data.get("amount")

        try:
            student_fee, payment_school = get_student_fee_for_online_payment(
                request.user, student_fee_id
            )
        except StudentFee.DoesNotExist:
            return Response(
                {"error": "Student fee not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if student_fee.status == "cancelled":
            return Response(
                {"error": "Payment cannot be created for a cancelled fee"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        student_fee.apply_late_fee()

        try:
            amount = (
                Decimal(str(requested_amount))
                if requested_amount
                else student_fee.balance_amount
            )
        except Exception:
            return Response(
                {"error": "Invalid amount"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {"error": "Amount must be greater than 0"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount > student_fee.balance_amount:
            return Response(
                {
                    "error": f"Amount cannot be greater than remaining balance {student_fee.balance_amount}"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_in_paise = int(amount * 100)
        razor_order = client.order.create(
            {
                "amount": amount_in_paise,
                "currency": "INR",
                "payment_capture": 1,
                "notes": {
                    "student_fee_id": str(student_fee.id),
                    "student_id": str(student_fee.student_id),
                    "fee_type": student_fee.feetype.name or "",
                },
            }
        )

        payment = StudentFeePayment.objects.create(
            school=payment_school,
            student_fee=student_fee,
            amount=amount,
            payment_mode="online",
            razorpay_order_id=razor_order["id"],
            collected_by=request.user,
            is_verified=False,
        )

        return Response(
            {
                "key": settings.RAZOR_PAY_KEY_ID,
                "order_id": razor_order["id"],
                "amount": razor_order["amount"],
                "currency": razor_order["currency"],
                "student_fee": student_fee.id,
                "payment": payment.id,
                "balance_amount": student_fee.balance_amount,
            },
            status=status.HTTP_201_CREATED,
        )


class StudentFeeRazorpayVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get("razorpay_order_id")
        payment_id = request.data.get("razorpay_payment_id")
        signature = request.data.get("razorpay_signature")

        if not all([order_id, payment_id, signature]):
            return Response(
                {"error": "Missing Razorpay payment parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        message = f"{order_id}|{payment_id}"
        generated_signature = hmac.new(
            settings.RAZOR_PAY_SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(generated_signature, signature):
            return Response(
                {"status": "failed", "error": "Invalid payment signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payment = get_student_fee_payment_for_online_verify(
                request.user,
                order_id,
            )
        except StudentFeePayment.DoesNotExist:
            return Response(
                {"error": "Payment order not found"}, status=status.HTTP_404_NOT_FOUND
            )

        if payment.is_verified:
            return Response(
                {
                    "status": "success",
                    "message": "Payment already verified",
                    "payment": StudentFeePaymentSerializer(payment).data,
                }
            )

        with transaction.atomic():
            payment.razorpay_payment_id = payment_id
            payment.razorpay_signature = signature
            payment.transaction_id = payment_id
            payment.is_verified = True
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.payment_date = timezone.now()
            if not payment.receipt_number:
                payment.receipt_number = f"RZP-{payment.id}"
            payment.save()
            payment.student_fee.refresh_payment_status()

        return Response(
            {
                "status": "success",
                "payment": StudentFeePaymentSerializer(payment).data,
                "student_fee": StudentFeeSerializer(payment.student_fee).data,
            }
        )


class StaffListView(ModelViewSet):
    queryset = Staff.objects.all()
    
    serializer_class = StaffListSirializer
    permission_classes = [IsAuthenticated,IsFeeManager]
    
    def get_queryset(self):
        return Staff.objects.filter(school = self.request.user.school)
    

class SchoolQuerySetMixin:
    def get_queryset(self):
        return self.queryset.filter(
            school=self.request.user.school
        )
        
class SchoolViewSet(ModelViewSet):
    queryset = School.objects.all()
    serializer_class = SchoolSerializer
    
# class WorkingDayViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = WorkingDay.objects.all()
#     serializer_class = WorkingDaySerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)

# class HolidayViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = Holiday.objects.all()
#     serializer_class = HolidaySerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)

# class StandardViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = Division.objects.all()
#     serializer_class = ClassDivSerializer
#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)
        
# class SubjectViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = Subject.objects.all()
#     serializer_class = SubjectSerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)
        

# class TeacherStaffViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = Staff.objects.all()
#     serializer_class = TeacherStaffSerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)
        

# class TimetableViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = Timetable.objects.all()
#     serializer_class = TimetableSerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)
        

# class LectureSlotViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = LectureSlot.objects.all()
#     serializer_class = LectureSlotSerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)
        

# class BreakSlotViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = BreakSlot.objects.all()
#     serializer_class = BreakSlotSerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)

# class TimetableEntryViewSet(SchoolQuerySetMixin, ModelViewSet):
#     queryset = TimetableEntry.objects.all()
#     serializer_class = TimetableEntrySerializer

#     def perform_create(self, serializer):
#         serializer.save(school=self.request.user.school)




from rest_framework.viewsets import ModelViewSet
from .models import Time_Table_tb
# from .serializers import TimeTableSerializer


class TimeTableViewSet(ModelViewSet):

    serializer_class = TimeTableSerializer
    permission_classes = [IsAuthenticated,IsCLerk]

    queryset = Time_Table_tb.objects.all()

    def get_queryset(self):

        return self.queryset.filter(
            school=self.request.user.school
        )

    def perform_create(self, serializer):

        serializer.save(
            school=self.request.user.school
        )
        
    def create(self, request, *args, **kwargs):
        response =  super().create(request, *args, **kwargs)
        
        return Response({
            "message":"Time Table Created Successfully"
        })
        
# ----------------------------------------------------------
# ATTENDANCE


class AttendanceStudentAPIView(APIView):

    def get(self, request):

        school = request.user.school

        teacher = request.user.staff

        # GET CLASS TEACHER ASSIGNMENT
        assign_class = AssignClass.objects.select_related(
            "division"
        ).filter(
            school=school,
            teacher=teacher,
            is_class_teacher=True
        ).first()

        # IF TEACHER NOT CLASS TEACHER
        if not assign_class:

            return Response(
                {
                    "success": False,
                    "message": (
                        "You are not assigned "
                        "as class teacher"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # GET STUDENTS
        students = Student.objects.filter(
            school=school,
            division=assign_class.division.division
        ).order_by("gr_no")

        serializer = StudentSerializer(
            students,
            many=True
        )

        return Response(
            {
                "success": True,

                "division_id": (
                    assign_class.division.id
                ),

                "division_name": (
                    str(assign_class.division)
                ),

                "total_students": students.count(),

                "students": serializer.data
            }
        )
    


# views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import StudentAttendance


class StudentAttendanceView(APIView):

    def get(self, request):

        queryset = StudentAttendance.objects.filter(
            school=request.user.school
        ).select_related(
            "student",
            "attendance_by",
        )

        serializer = StudentAttendanceSerializer(
            queryset,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):

        serializer = StudentAttendanceSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        serializer.save()

        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED
        )





# from .homework_serializer import (
#     HomeworkSerializer,
#     GetHomeworkSerializer,
#     HomeworkSubmissionSerializer,
#     HomeworkSubmissionDetailSerializer,
#     CheckHomeworkSubmissionSerializer,
#     StudentHomeworkListSerializer,
# )


class HomeworkViewSet(ModelViewSet):
    """
    ViewSet for managing homework.
    
    Actions:
    - CREATE: Teachers create homework for a division
    - LIST: Get all homework (teachers see all, students see their division's)
    - RETRIEVE: Get homework details
    - UPDATE: Teachers update homework
    - DESTROY: Teachers delete homework
    - student-homework: Students view homework for their division
    """
    
    permission_classes = [IsAuthenticated]
    queryset = Homework.objects.all()

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "student_homework":
            return GetHomeworkSerializer
        elif self.action == "list" and self.is_student():
            return GetHomeworkSerializer
        return HomeworkSerializer

    def get_queryset(self):
        """Filter homework by school"""
        school = self.request.user.school
        queryset = Homework.objects.filter(school=school).select_related(
            "division", "teacher", "division__SchoolClass"
        )

        # If user is a student, only show homework for their division
        if self.is_student():
            try:
                student = self.request.user.student
                queryset = queryset.filter(division__division=student.division)
            except Student.DoesNotExist:
                queryset = queryset.none()

        return queryset.order_by("-assigned_date")

    def is_student(self):
        """Check if logged-in user is a student"""
        try:
            return hasattr(self.request.user, "student")
        except:
            return False

    def is_teacher(self):
        """Check if logged-in user is a teacher (has staff profile)"""
        try:
            return hasattr(self.request.user, "staff")
        except:
            return False

    def create(self, request, *args, **kwargs):
        """Only teachers can create homework"""
        if not self.is_teacher():
            return Response(
                {"error": "Only teachers can create homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Only the teacher who created can update homework"""
        homework = self.get_object()
        
        if homework.teacher.user != request.user:
            return Response(
                {"error": "You can only update homework you created."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Only the teacher who created can delete homework"""
        homework = self.get_object()
        
        if homework.teacher.user != request.user:
            return Response(
                {"error": "You can only delete homework you created."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["get"])
    def student_homework(self, request):
        """
        Get all homework for the logged-in student's division.
        Students can use this endpoint to view all homework for their class.
        """
        if not self.is_student():
            return Response(
                {"error": "Only students can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            student = request.user.student
        except Student.DoesNotExist:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not student.division:
            return Response(
                {"error": "Student division not assigned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def submissions(self, request, pk=None):
        """
        Get all submissions for a specific homework.
        Only the teacher who created the homework can view submissions.
        """
        homework = self.get_object()

        if homework.teacher.user != request.user:
            return Response(
                {"error": "You can only view submissions for your homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        submissions = homework.submissions.select_related("student", "checked_by")
        serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def division_details(self, request, pk=None):
        """Get division details for this homework"""
        homework = self.get_object()
        division = homework.division
        
        return Response({
            "division_id": division.id,
            "division_name": division.division,
            "school_class": division.SchoolClass.get_school_class_display(),
            "total_students": Student.objects.filter(school_class=division.SchoolClass, division=division.division, school=request.user.school).count(),
            "submitted_count": homework.submissions.filter(status__in=["submitted", "checked"]).values("student").distinct().count(),
        })


class HomeworkSubmissionViewSet(ModelViewSet):
    """
    ViewSet for managing homework submissions.
    
    Actions:
    - CREATE: Students submit homework
    - LIST: Get submissions (students see their own, teachers see all for their homework)
    - RETRIEVE: Get submission details
    - UPDATE: Update submission (teacher can grade)
    - check-submission: Teacher grades the submission
    """
    
    permission_classes = [IsAuthenticated]
    queryset = HomeworkSubmission.objects.all()
    serializer_class = HomeworkSubmissionSerializer

    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == "check_submission":
            return CheckHomeworkSubmissionSerializer
        elif self.action == "retrieve":
            return HomeworkSubmissionDetailSerializer
        return HomeworkSubmissionSerializer

    def get_queryset(self):
        """Filter submissions based on user role"""
        school = self.request.user.school
        queryset = HomeworkSubmission.objects.filter(school=school).select_related(
            "homework", "student", "checked_by"
        )

        # If user is a student, only show their own submissions
        if self.is_student():
            try:
                student = self.request.user.student
                queryset = queryset.filter(student=student)
            except:
                queryset = queryset.none()

        # If user is a teacher, only show submissions for their homework
        elif self.is_teacher():
            try:
                staff = self.request.user.staff
                queryset = queryset.filter(homework__teacher=staff)
            except:
                queryset = queryset.none()

        return queryset.order_by("-submitted_at", "-created_at")

    def is_student(self):
        """Check if logged-in user is a student"""
        try:
            return hasattr(self.request.user, "student")
        except:
            return False

    def is_teacher(self):
        """Check if logged-in user is a teacher"""
        try:
            return hasattr(self.request.user, "staff")
        except:
            return False

    def create(self, request, *args, **kwargs):
        """
        Students submit homework.
        Automatically sets the student to the logged-in user's student profile.
        """
        if not self.is_student():
            return Response(
                {"error": "Only students can submit homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Automatically set student from request user
        try:
            student = request.user.student
        except Student.DoesNotExist:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Add student to request data
        request.data._mutable = True
        request.data["student"] = student.id
        request.data._mutable = False

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """Teachers can only grade submissions (not modify student's submission)"""
        submission = self.get_object()

        if not self.is_teacher():
            return Response(
                {"error": "Only teachers can grade submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if submission.homework.teacher.user != request.user:
            return Response(
                {"error": "You can only grade submissions for your homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Only allow updating status, marks, and remarks
        allowed_fields = {"status", "marks", "teacher_remark"}
        provided_fields = set(request.data.keys())
        invalid_fields = provided_fields - allowed_fields

        if invalid_fields:
            return Response(
                {"error": f"Cannot update fields: {', '.join(invalid_fields)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Students can delete their own submissions, teachers cannot delete"""
        submission = self.get_object()

        if self.is_teacher():
            return Response(
                {"error": "Teachers cannot delete submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if self.is_student():
            try:
                student = request.user.student
                if submission.student != student:
                    return Response(
                        {"error": "You can only delete your own submissions."},
                        status=status.HTTP_403_FORBIDDEN,
                    )
            except Student.DoesNotExist:
                pass

        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def check_submission(self, request, pk=None):
        """
        Teacher grades a submission.
        Endpoint to mark a submission as checked with marks and remarks.
        """
        submission = self.get_object()

        if not self.is_teacher():
            return Response(
                {"error": "Only teachers can grade submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if submission.homework.teacher.user != request.user:
            return Response(
                {"error": "You can only grade submissions for your homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(submission, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def pending_submissions(self, request):
        """Get all pending submissions for the teacher"""
        if not self.is_teacher():
            return Response(
                {"error": "Only teachers can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            staff = request.user.staff
        except:
            return Response(
                {"error": "Staff profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        submissions = self.get_queryset().filter(status__in=["pending", "submitted"])
        serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_submissions(self, request):
        """Get all submissions from the logged-in student"""
        if not self.is_student():
            return Response(
                {"error": "Only students can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            student = request.user.student
        except:
            return Response(
                {"error": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        submissions = self.get_queryset().filter(student=student)
        serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def submission_stats(self, request, **kwargs):
        """Get submission statistics for a homework"""
        homework_id = request.query_params.get("homework_id")

        if not homework_id:
            return Response(
                {"error": "homework_id query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            homework = Homework.objects.get(id=homework_id, school=request.user.school)
        except Homework.DoesNotExist:
            return Response(
                {"error": "Homework not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if homework.teacher.user != request.user:
            return Response(
                {"error": "You can only view stats for your homework."},
                status=status.HTTP_403_FORBIDDEN,
            )

        submissions = homework.submissions.all()
        total_students = Student.objects.filter(school_class=homework.division.SchoolClass, division=homework.division.division, school=request.user.school).count()

        return Response({
            "homework_id": homework.id,
            "homework_title": homework.title,
            "total_students": total_students,
            "submitted": submissions.filter(status__in=["submitted", "checked"]).count(),
            "pending": submissions.filter(status="pending").count(),
            "late": submissions.filter(status="late").count(),
            "checked": submissions.filter(status="checked").count(),
            "average_marks": submissions.filter(marks__isnull=False).aggregate(
                avg=models.Avg("marks")
            )["avg"] or 0,
        })
