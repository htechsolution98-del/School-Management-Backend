from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
# pyrefly: ignore [missing-import]
from rest_framework.viewsets import ModelViewSet
# pyrefly: ignore [missing-import]
from rest_framework import generics
# pyrefly: ignore [missing-import]
from rest_framework.response import Response
# pyrefly: ignore [missing-import]
from rest_framework import status
# pyrefly: ignore [missing-import]
from django.contrib.auth import authenticate
# pyrefly: ignore [missing-import]
from django.utils import timezone
from .models import *
from .serializer import *
from .permissions import *
from .utils import *
import datetime
from decimal import Decimal
from .staff_serializers import *

# pyrefly: ignore [missing-import]
from django.core.cache import cache
# pyrefly: ignore [missing-import]
from django.db import transaction
# pyrefly: ignore [missing-import]
from rest_framework.permissions import IsAuthenticated
# pyrefly: ignore [missing-import]
from rest_framework.decorators import api_view, permission_classes
# pyrefly: ignore [missing-import]
from django.contrib.auth.models import Group
# pyrefly: ignore [missing-import]
from django.contrib.auth import get_user_model
from rest_framework.exceptions import PermissionDenied

User = get_user_model()

class DepartmentViewSet(ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, IsClerkOrTrustee | IsClerkOrPrincipal]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            staff = getattr(user, 'staff', None)
            if staff and staff.school:
                school = staff.school
        if school:
            return Department.objects.filter(school=school)
        return Department.objects.filter(school__login_id=user)

    def perform_create(self, serializer):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            staff = getattr(user, 'staff', None)
            if staff and staff.school:
                school = staff.school
        if not school:
            school = getattr(user, 'managed_school', None)
            if not school:
                school = School.objects.filter(login_id=user.id).first()
        if not school:
            raise PermissionDenied("You must belong to a school to create a department.")
        name = serializer.validated_data.get('name')
        if name and Department.objects.filter(school=school, name__iexact=name).exists():
            raise serializers.ValidationError({"name": "A department with this name already exists in your school."})
        serializer.save(school=school)

class StaffView(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, IsClerkOrTrustee | IsClerkOrPrincipal]

    # 🔹 Get staff list filtered by user's school
    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            staff = getattr(user, 'staff', None)
            if staff and staff.school:
                school = staff.school
        if school:
            return Staff.objects.filter(school=school)
        # Fallback for trustee who may be the school owner (login_id)
        return Staff.objects.filter(school__login_id=user)

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

        creator = self.request.user
        school = getattr(creator, 'school', None)
        if not school:
            school = getattr(creator, 'managed_school', None)
        if not school:
            school = School.objects.filter(login_id=creator.id).first()

        # Enforce that category/feature must be enabled by SuperAdmin for this school
        if school and not SchoolFeature.objects.filter(school=school, feature=cat, is_enabled=True).exists():
            raise serializers.ValidationError({"category": f"Feature '{cat.name}' is not enabled by Superadmin for this school."})

        group = Group.objects.filter(name__iexact=cat.name).first()
        if not group:
            group = Group.objects.create(name=cat.name)

        username = generate_staff_username(name)

        with transaction.atomic():
            user = User(username=username)
            user.school = self.request.user.school
            user.role = (
                cat.name
            )  # ---------------------------------- THIS IS CHANGE ===category
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

        school = getattr(self.request.user, 'school', None)
        if not school:
            school = School.objects.filter(login_id=self.request.user).first()

        instance = serializer.save(user=user, school=school, category=cat.name)

        # Broadcast staff status event
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer and school:
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_choice_all",
                    {"type": "staff_status_changed", "action": "created"},
                )
        except Exception as e:
            print("Failed to broadcast staff event:", e)

    def perform_update(self, serializer):
        category = serializer.validated_data.pop("category", None)
        instance = serializer.save()
        user = instance.user
        if user:
            if instance.name:
                user.first_name = instance.name
            if instance.email:
                user.email = instance.email
            if instance.mobile:
                user.mobile = instance.mobile
            if instance.is_active is not None:
                user.is_active = instance.is_active
            user.save()

        if category is not None:
            try:
                category_id = int(category)
                cat = Feature.objects.filter(id=category_id).first()
                if cat:
                    instance.category = cat.name
                    instance.save(update_fields=["category"])
                    if user:
                        user.role = cat.name
                        user.save(update_fields=["role"])
                        group = Group.objects.filter(name__iexact=cat.name).first()
                        if not group:
                            group = Group.objects.create(name=cat.name)
                        user.groups.clear()
                        user.groups.add(group)
                        UserModuleAccess.objects.filter(user=user).delete()
                        modules = Module.objects.filter(for_role=category_id)
                        for m in modules:
                            UserModuleAccess.objects.create(user=user, module=m)
                else:
                    instance.category = str(category)
                    instance.save(update_fields=["category"])
            except (ValueError, TypeError):
                instance.category = str(category)
                instance.save(update_fields=["category"])

        school = instance.school or getattr(self.request.user, 'school', None)
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            if channel_layer and school:
                async_to_sync(channel_layer.group_send)(
                    f"school_{school.id}_choice_all",
                    {"type": "staff_status_changed", "action": "updated"},
                )
        except Exception as e:
            print("Failed to broadcast staff update:", e)

        cache.delete(f"staff_list_{self.request.user.id}")

    # 🔹 Delete staff + clear cache
    def perform_destroy(self, instance):
        instance.delete()
        cache.delete(f"staff_list_{self.request.user.id}")




class GetTeacherView(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = GetTeacherSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]
    http_method_names = ["get"]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            staff = getattr(user, 'staff', None)
            if staff and staff.school:
                school = staff.school
        if not school:
            school = getattr(user, 'managed_school', None)
        if not school:
            school = School.objects.filter(login_id=user.id).first()

        qs = Staff.objects.all()
        if school:
            qs = qs.filter(school=school)
        elif not user.is_superuser:
            return Staff.objects.none()

        teacher_qs = qs.filter(
            Q(user__groups__name__icontains="teacher") |
            Q(category__icontains="teacher") |
            Q(user__role__icontains="teacher")
        ).distinct()

        if teacher_qs.exists():
            return teacher_qs

        active_qs = qs.filter(is_active=True)
        return active_qs if active_qs.exists() else qs


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




class StaffListView(ModelViewSet):
    queryset = Staff.objects.all()

    serializer_class = StaffListSirializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Staff.objects.filter(school=self.request.user.school)




class StaffFaceEnrollView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            return Response(
                {"error": "Staff profile not found for this user"},
                status=404
            )
        serializer = StaffFaceSerializer(
            data=request.data,
            context={
                "request": request,
                "staff": staff,
            }
        )
        if serializer.is_valid():
            face_obj = serializer.save()
        
            return Response({
                "message": "Face enroll successfully.",
                "staff": staff.id,
                "face_id": face_obj.id
            })

        return Response(serializer.errors, status=400)
    
import requests
import io

# pyrefly: ignore [missing-import]
from PIL import Image
# pyrefly: ignore [missing-import]
from django.conf import settings
# pyrefly: ignore [missing-import]
from rest_framework.views import APIView
# pyrefly: ignore [missing-import]
from rest_framework.response import Response
# pyrefly: ignore [missing-import]
from rest_framework.permissions import IsAuthenticated
# pyrefly: ignore [missing-import]
from rest_framework import status


# -------------------------
# Image Optimization Helper
# -------------------------


class StaffFaceVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        staff = Staff.objects.filter(user=request.user).first()
        if not staff:
            return Response({"enrolled": False, "is_enrolled": False}, status=status.HTTP_200_OK)
        enrolled = StaffFace.objects.filter(staff=staff, is_enrolled=True).exists()
        return Response({"enrolled": enrolled, "is_enrolled": enrolled}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = StaffFaceVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_image = serializer.validated_data["image"]
        purpose = request.data.get("purpose", "ATTENDANCE_PUNCH")

        # get staff
        staff = Staff.objects.filter(user=request.user).first()
        if not staff and getattr(request.user, "email", None):
            staff = Staff.objects.filter(email=request.user.email).first()
        if not staff and getattr(request.user, "mobile", None):
            staff = Staff.objects.filter(mobile=request.user.mobile).first()

        if not staff:
            return Response(
                {"error": "Staff profile not found for current user."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        school = staff.school or getattr(request.user, "school", None)
        allow_bypass = settings.DEBUG or getattr(settings, "ALLOW_BIOMETRIC_BYPASS", False)

        try:
            staff_face = StaffFace.objects.get(staff=staff, is_enrolled=True)
        except StaffFace.DoesNotExist:
            if allow_bypass:
                proof = generate_biometric_proof(
                    staff=staff,
                    school=school,
                    purpose=purpose,
                    confidence=Decimal("99.00"),
                )
                return Response(
                    {
                        "verified": True,
                        "confidence": 99.0,
                        "token": proof.token,
                        "verification_token": proof.token,
                        "bypass": True,
                        "message": "Development mode face bypass active (face not enrolled).",
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"error": "Face not enrolled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enrolled_image = staff_face.face_image

        # -------------------------
        # OPTIMIZE BOTH IMAGES
        # -------------------------
        enrolled_image.open("rb")
        optimized_enrolled = optimize_image(enrolled_image)
        optimized_uploaded = optimize_image(uploaded_image)

        # -------------------------
        # FACE++ REQUEST (15s timeout)
        # -------------------------
        try:
            response = requests.post(
                "https://api-us.faceplusplus.com/facepp/v3/compare",
                data={
                    "api_key": settings.FACEPP_API_KEY,
                    "api_secret": settings.FACEPP_API_SECRET,
                },
                files={
                    "image_file1": ("enrolled.jpg", optimized_enrolled, "image/jpeg"),
                    "image_file2": ("live.jpg", optimized_uploaded, "image/jpeg"),
                },
                timeout=15,
            )
        except requests.exceptions.RequestException as e:
            if allow_bypass:
                proof = generate_biometric_proof(
                    staff=staff,
                    school=school,
                    purpose=purpose,
                    confidence=Decimal("95.00"),
                )
                return Response(
                    {
                        "verified": True,
                        "confidence": 95.0,
                        "token": proof.token,
                        "verification_token": proof.token,
                        "bypass": True,
                        "warning": f"Face++ request failed ({str(e)}), used dev bypass.",
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"error": f"Face++ request failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # -------------------------
        # RESPONSE HANDLING
        # -------------------------
        try:
            result = response.json()
        except Exception:
            result = {"error": response.text}

        if response.status_code != 200:
            if allow_bypass:
                proof = generate_biometric_proof(
                    staff=staff,
                    school=school,
                    purpose=purpose,
                    confidence=Decimal("95.00"),
                )
                return Response(
                    {
                        "verified": True,
                        "confidence": 95.0,
                        "token": proof.token,
                        "verification_token": proof.token,
                        "bypass": True,
                        "warning": f"Face++ error {response.status_code}, used dev bypass.",
                    },
                    status=status.HTTP_200_OK,
                )
            return Response(
                {"error": result},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            confidence = float(result.get("confidence", 0) or 0)
        except (ValueError, TypeError):
            confidence = 0.0
        verified = confidence >= 80.0

        response_data = {
            "verified": verified,
            "confidence": confidence,
            "raw_response": result,
        }

        if verified:
            proof = generate_biometric_proof(
                staff=staff,
                school=school,
                purpose=purpose,
                confidence=Decimal(str(confidence)),
            )
            response_data["token"] = proof.token
            response_data["verification_token"] = proof.token
        elif allow_bypass and (request.data.get("bypass") or request.query_params.get("bypass")):
            proof = generate_biometric_proof(
                staff=staff,
                school=school,
                purpose=purpose,
                confidence=Decimal("90.00"),
            )
            response_data["verified"] = True
            response_data["bypass"] = True
            response_data["token"] = proof.token
            response_data["verification_token"] = proof.token

        return Response(response_data, status=status.HTTP_200_OK)

# class ParentCreateView(APIView):

#     def post(self, request):

#         serializer = ParentCreateSerializer(
#             data=request.data
#         )

#         if serializer.is_valid():

#             parent = serializer.save()

#             return Response(
#                 {
#                     "message": "Parent created successfully",
#                     "parent_id": parent.id,
#                 },
#                 status=status.HTTP_201_CREATED,
#             )

#         return Response(
#             serializer.errors,
#             status=status.HTTP_400_BAD_REQUEST,
#         )





class GetRemainingLeavePerStaffView(APIView):
    permission_classes=[IsAuthenticated]
    def get(self,request):
        leave=LeaveRequest.objects.filter(staff=request.user.staff,school=request.user.school).order_by("-created_at")
        
        # leave_template=LeaveTemplate.objects.filter(staff=request.user.staff,school=request.user.school)
        # print(leave_template)
        remaining_leaves=StaffRemainingLeave.objects.filter(staff=request.user.staff,school=request.user.school).order_by("year","month")
        
        leave_request=LeaveRequestSerializer(leave,many=True)
        remaining_leaves_left=StaffRemainingLeaveSerializer(remaining_leaves,many=True)
        return Response({
            "Leave_request":leave_request.data,
            "reamining_leaves":remaining_leaves_left.data
        })

# class AnnouncementView(ModelViewSet):
#     queryset = Announcement.objects.all()
#     serializer_class = AnnouncementSerializer
#     permission_classes = [IsAuthenticated, Isprincipal]


# class GetAnnouncementView(ModelViewSet):
#     queryset = Announcement.objects.all()
#     serializer_class = GetAnnouncementSerializer
#     permission_classes = [IsAuthenticated]

#     def get_queryset(self):
#         user = self.request.user
#         now = timezone.now()

#         print(user.id)
#         print(type(user.id))
#         # Base filter (active announcements)
#         base_filter = Q(school=user.school, publish_at__lte=now) & (
#             Q(expires_at__gte=now) | Q(expires_at__isnull=True)
#         )

#         # ALL users
#         # all_filter = Q(targets__target_type='ALL')

#         # SPECIFIC user
#         specific_filter = Q(targets__target_type="SPECIFIC", targets__target_id=user.id)

#         # ROLE-based
#         user_groups = user.groups.values_list("id", flat=True)
#         print(user_groups)
#         role_filter = Q(targets__target_type="ROLE", targets__target_id__in=user_groups)

#         # 4️ CLASS-based (only if student)
#         class_filter = Q()
#         if hasattr(user, "student"):
#             class_filter = Q(
#                 targets__target_type="CLASS",
#                 targets__target_id=user.student.school_class_id,
#             )

#         # Combine everything
#         queryset = Announcement.objects.filter(specific_filter | base_filter).order_by(
#             "-created_at"
#         )

#         return queryset

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
# pyrefly: ignore [missing-import]
from django.db import transaction
# pyrefly: ignore [missing-import]
from rest_framework.views import APIView
# pyrefly: ignore [missing-import]
from rest_framework.response import Response
# pyrefly: ignore [missing-import]
from rest_framework.permissions import IsAuthenticated

# from yourapp.models import Student, SchoolClass, School
# from yourapp.permissions import IsCLerk


from rest_framework.decorators import action
from django.db.models import Q


class TeacherWorkloadViewSet(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = TeacherWorkloadSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch", "put", "head", "options"]

    def get_school(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            staff = getattr(user, "staff", None)
            if staff and staff.school:
                school = staff.school
        return school

    def get_queryset(self):
        school = self.get_school()
        if not school:
            return Staff.objects.none()

        queryset = (
            Staff.objects.filter(school=school)
            .filter(
                Q(category__iexact="teacher")
                | Q(user__groups__name__iexact="teacher")
                | Q(assignclass__isnull=False)
            )
            .select_related("department", "user")
            .distinct()
            .order_by("name", "id")
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(department__name__icontains=search)
            )

        return queryset

    @action(detail=False, methods=["patch", "post"], url_path="bulk-update")
    def bulk_update(self, request):
        school = self.get_school()
        if not school:
            return Response({"detail": "School not found."}, status=status.HTTP_400_BAD_REQUEST)

        teacher_ids = request.data.get("teacher_ids", [])
        update_fields = {}

        # Support uniform daily limit
        uniform_daily = request.data.get("uniform_daily_periods") or request.data.get("max_daily_periods")
        if uniform_daily is not None:
            val = int(uniform_daily)
            if val < 0 or val > 15:
                return Response({"detail": "Daily limit must be between 0 and 15."}, status=status.HTTP_400_BAD_REQUEST)
            for d in ["mon", "tue", "wed", "thu", "fri", "sat"]:
                update_fields[f"max_periods_{d}"] = val

        # Individual day fields
        for d in ["mon", "tue", "wed", "thu", "fri", "sat"]:
            f = f"max_periods_{d}"
            if f in request.data:
                val = int(request.data[f])
                if val < 0 or val > 15:
                    return Response({"detail": f"{d.capitalize()} limit must be between 0 and 15."}, status=status.HTTP_400_BAD_REQUEST)
                update_fields[f] = val

        max_weekly = request.data.get("max_weekly_periods")
        max_consecutive = request.data.get("max_consecutive_periods")

        if max_weekly is not None:
            val = int(max_weekly)
            if val < 1 or val > 60:
                return Response({"detail": "Weekly limit must be between 1 and 60."}, status=status.HTTP_400_BAD_REQUEST)
            update_fields["max_weekly_periods"] = val
        if max_consecutive is not None:
            val = int(max_consecutive)
            if val < 1 or val > 10:
                return Response({"detail": "Consecutive limit must be between 1 and 10."}, status=status.HTTP_400_BAD_REQUEST)
            update_fields["max_consecutive_periods"] = val

        if not update_fields:
            return Response({"detail": "No valid fields provided to update."}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset()
        if teacher_ids:
            qs = qs.filter(id__in=teacher_ids)

        updated_count = qs.update(**update_fields)
        return Response({"message": f"Successfully updated {updated_count} teachers.", "count": updated_count})

