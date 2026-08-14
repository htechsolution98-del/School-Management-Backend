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
    permission_classes = [IsAuthenticated, IsClerkOrTrustee]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
        if school:
            return Department.objects.filter(school=school)
        return Department.objects.filter(school__login_id=user)

    def perform_create(self, serializer):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            school = getattr(user, 'managed_school', None)
            if not school:
                school = School.objects.filter(login_id=user.id).first()
        if not school:
            raise PermissionDenied("You must belong to a school to create a department.")
        serializer.save(school=school)

class StaffView(ModelViewSet):
    queryset = Staff.objects.all()
    serializer_class = StaffSerializer
    permission_classes = [IsAuthenticated, IsClerkOrTrustee]

    # 🔹 Get staff list filtered by user's school
    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
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
        if creator.groups.filter(name="admin(trustee)").exists():
            if cat.name != "CLERK":
                raise PermissionDenied("Trustee can only create Clerk users.")
        elif creator.groups.filter(name="CLERK").exists():
            allowed_roles = ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL", "FEES MANAGEMENT", "TEACHER", "INVENTORY", "LIBRARIAN", "TRANSPORTATION"]
            if cat.name not in allowed_roles:
                raise PermissionDenied(f"Clerk cannot create {cat.name} users.")

        group, created = Group.objects.get_or_create(name=cat.name)

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

        serializer.save(user=user, school=school, category=cat.name)

    def perform_update(self, serializer):
        category = serializer.validated_data.pop("category", None)
        if category is not None:
            try:
                category_id = int(category)
                cat = Feature.objects.filter(id=category_id).first()
                if cat:
                    instance = serializer.save(category=cat.name)
                    user = instance.user
                    if user:
                        user.role = cat.name
                        user.save()
                        # Update group
                        group, _ = Group.objects.get_or_create(name=cat.name)
                        user.groups.clear()
                        user.groups.add(group)
                        
                        # Update module access
                        UserModuleAccess.objects.filter(user=user).delete()
                        modules = Module.objects.filter(for_role=category_id)
                        for m in modules:
                            UserModuleAccess.objects.create(user=user, module=m)
                else:
                    serializer.save(category=category)
            except (ValueError, TypeError):
                serializer.save(category=category)
        else:
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

    def post(self, request):

        serializer = StaffFaceVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_image = serializer.validated_data["image"]

        # get staff
        try:
            staff = Staff.objects.get(user=request.user)

            staff_face = StaffFace.objects.get(
                staff=staff,
                is_enrolled=True
            )

        except StaffFace.DoesNotExist:
            return Response(
                {"error": "Face not enrolled."},
                status=status.HTTP_400_BAD_REQUEST
            )

        enrolled_image = staff_face.face_image

        # -------------------------
        # OPTIMIZE BOTH IMAGES
        # -------------------------
        enrolled_image.open("rb")

        optimized_enrolled = optimize_image(enrolled_image)
        optimized_uploaded = optimize_image(uploaded_image)

        # -------------------------
        # FACE++ REQUEST
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
                timeout=30
            )

        except requests.exceptions.RequestException as e:
            return Response(
                {"error": f"Face++ request failed: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # -------------------------
        # RESPONSE HANDLING
        # -------------------------
        result = response.json()

        if response.status_code != 200:
            return Response(
                {"error": result},
                status=status.HTTP_400_BAD_REQUEST
            )

        confidence = result.get("confidence", 0)
        verified = confidence >= 80

        return Response({
            "verified": verified,
            "confidence": confidence,
            "raw_response": result
        })

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


# ----------------------------
# Helpers
# ----------------------------




