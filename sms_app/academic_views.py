from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework import generics
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from django.utils import timezone
from django.shortcuts import get_object_or_404
from .models import *
from .serializer import *
from .academic_serializers import AssignClassSerializer, ClassCategorySerializer
from .permissions import *
from .utils import *
import datetime
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes, action

class DashboardCountAPIView(APIView):
    permission_classes = [IsAuthenticated, Isprincipal]

    def get(self, request):
        school = request.user.school

        if not school:
            return Response(
                {"message": "User does not have a school assigned"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total_student = Student.objects.filter(school=school).count()
        total_staff = (
            Staff.objects.filter(school=school)
            .exclude(category__iexact="PRINCIPAL")
            .count()
        )
        admission_not_complete = (
            Admission.objects.filter(school=school).exclude(status="completed").count()
        )

        return Response(
            {
                "total_student": total_student,
                "total_staff": total_staff,
                "admission_not_complete": admission_not_complete,
            },
            status=status.HTTP_200_OK,
        )




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




class ClassCategoryViewSet(ModelViewSet):
    queryset = ClassCategory.objects.all()
    serializer_class = ClassCategorySerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return ClassCategory.objects.none()
        
        school = user.school
        if not school:
            return ClassCategory.objects.none()

        return ClassCategory.objects.filter(school=school)
    
    def perform_create(self, serializer):
        user = getattr(self.request, "user", None)
        serializer.save(school=user.school)


class SchoolClassView(ModelViewSet):
    queryset = SchoolClass.objects.all()
    serializer_class = SchoolClassSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]

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

        existing = Division.objects.filter(
            school=self.request.user.school,
            SchoolClass_id=school_class,
        ).count()
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
        
        from .views import assign_student_divisions
        assign_student_divisions()

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


class ListDivisionView(ModelViewSet):
    queryset = Division.objects.all()
    serializer_class = SetDivisionSerializer
    permission_classes = [IsAuthenticated, Isteacher]
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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subject.objects.filter(school=self.request.user.school)

    def _clear_cache(self):
        try:
            cache.clear()
        except Exception:
            pass

    # ✅ CREATE
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        instance = serializer.save(school=request.user.school)

        self._clear_cache()

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
        self._clear_cache()

    # DELETE
    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        self._clear_cache()

        instance.delete()


from django.core.cache import cache
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status




class SyllabusView(ModelViewSet):
    queryset = Syllabus.objects.all()
    serializer_class = SyllabusSerializer
    permission_classes = [IsAuthenticated]

    # ✅ Restrict to user's school
    def get_queryset(self):
        return Syllabus.objects.filter(school=self.request.user.school)

    def _clear_cache(self, school_id):
        try:
            cache.clear()
        except Exception:
            pass

    # ✅ CREATE
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        division = serializer.validated_data.get("division")
        subject = serializer.validated_data.get("subject")

        # Automatically replace/delete previous syllabus for same division & subject
        if division and subject:
            old_records = Syllabus.objects.filter(
                school=request.user.school,
                division=division,
                subject=subject,
            )
            for old in old_records:
                if old.syllabus_file:
                    try:
                        old.syllabus_file.delete(save=False)
                    except Exception:
                        pass
                old.delete()

        instance = serializer.save(school=request.user.school)
        self._clear_cache(request.user.school.id)

        return Response(
            {"message": "Syllabus uploaded successfully", "data": serializer.data},
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
                    "data": cached_data
                }
            )

        instance = self.get_object()
        serializer = self.get_serializer(instance)

        cache.set(cache_key, serializer.data, timeout=60 * 10)

        return Response({"message": "Data fetched from DB", "data": serializer.data})

    # ✅ UPDATE
    def perform_update(self, serializer):
        instance = serializer.save()
        self._clear_cache(instance.school.id)

    # ✅ DELETE
    def perform_destroy(self, instance):
        school_id = instance.school.id
        if instance.syllabus_file:
            try:
                instance.syllabus_file.delete(save=False)
            except Exception:
                pass
        instance.delete()
        self._clear_cache(school_id)




class AssignClassView(ModelViewSet):
    queryset = AssignClass.objects.all()
    serializer_class = AssignClassSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            return AssignClass.objects.none()

        queryset = AssignClass.objects.filter(school=school).select_related(
            "teacher", "subject", "division", "division__SchoolClass"
        )

        is_teacher_group = user.groups.filter(name__iexact="TEACHER").exists()
        is_clerk_admin = (
            user.is_superuser
            or user.is_staff
            or user.groups.filter(
                name__in=["CLERK", "FEES MANAGEMENT", "PRINCIPAL", "admin(trustee)"]
            ).exists()
        )

        my_assignments = self.request.query_params.get("my_assignments")

        if my_assignments == "true" or (is_teacher_group and not is_clerk_admin):
            if hasattr(user, "staff") and user.staff:
                queryset = queryset.filter(teacher=user.staff)

        return queryset


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


class GetLocationView(APIView):
    permission_classes = [IsAuthenticated, IsCLerk]

    def post(self, request):
        existing_instance = AttendanceLocation.objects.filter(school=request.user.school).first()
        serializer = AttendanceLocationSerializer(
            instance=existing_instance,
            data=request.data,
            partial=True,
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Location saved successfully"},
                status=status.HTTP_200_OK if existing_instance else status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        queryset = AttendanceLocation.objects.filter(school=request.user.school)

        serializer = AttendanceLocationSerializer(
            queryset, many=True, context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)





class DeleteUpdateLocationView(APIView):
    permission_classes = [IsAuthenticated, IsCLerk]

    def delete(self, request, pk):
        attendancelocation = get_object_or_404(AttendanceLocation, pk=pk)
        time_rule = attendancelocation.time_rule

        attendancelocation.delete()
        if time_rule:
            time_rule.delete()

        return Response(
            {"message": "Location deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )



#     def put(self,pk):
#         attendancelocation=get_object_or_404(AttendanceLocation,pk=pk)
#         serializer=AttendanceLocationSerializer(attendancelocation,data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors)

    



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
                {
                    "attendance_date": today,
                    "checked_in": False,
                    "checked_out": False,
                    "check_in": None,
                    "check_out": None,
                    "is_present": False,
                    "is_half_day": False,
                    "message": "Staff profile not found for current user.",
                },
                status=status.HTTP_200_OK,
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




class AcademicYearMainView(ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)




class AcademicYearViewSet(ModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    permission_classes = [IsAuthenticated, IsClerkOrPrincipal]
    http_method_names = ["get"]

    def get_queryset(self):
        return AcademicYear.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)




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
    permission_classes = [IsAuthenticated, IsCLerk]

    queryset = Time_Table_tb.objects.all()

    def get_queryset(self):

        return self.queryset.filter(school=self.request.user.school).select_related(
            "class_division", "class_division__SchoolClass"
        )

    def perform_create(self, serializer):

        serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        return Response({"message": "Time Table Created Successfully"})

    @action(detail=False, methods=["get"], url_path="creatable-divisions")
    def creatable_divisions(self, request):
        school = request.user.school
        all_days = [day for day, _ in Time_Table_tb.DAY_CHOICES]

        divisions = (
            Division.objects.filter(school=school)
            .select_related("SchoolClass")
            .order_by("SchoolClass_id", "division")
        )

        existing_rows = Time_Table_tb.objects.filter(
            school=school,
            class_division__in=divisions,
        ).values_list("class_division_id", "day")

        used_days_by_division = {}
        for division_id, day in existing_rows:
            used_days_by_division.setdefault(division_id, set()).add(day)

        data = []
        for division in divisions:
            used_days = used_days_by_division.get(division.id, set())
            creatable_days = [day for day in all_days if day not in used_days]

            data.append(
                {
                    "division_id": division.id,
                    "school_class": division.SchoolClass_id,
                    "school_class_name": division.SchoolClass.school_class,
                    "division": division.division,
                    "creatable_days": creatable_days,
                    "created_days": [day for day in all_days if day in used_days],
                    "can_create": bool(creatable_days),
                }
            )

        return Response(data)

    @action(detail=False, methods=["post"], url_path="auto-generate-preview")
    def auto_generate_preview(self, request):
        import random
        school = request.user.school
        if not school:
            return Response(
                {"error": "User does not have a school assigned"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        divisions = (
            Division.objects.filter(school=school)
            .select_related("SchoolClass")
            .order_by("SchoolClass_id", "division")
        )

        if not divisions.exists():
            return Response(
                {"error": "No class divisions found for this school."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Validation: Ensure ALL divisions have a Class Teacher assigned
        missing_ct_divisions = []
        ct_by_division = {}
        assignments_by_division = {}

        for div in divisions:
            ct_assign = (
                AssignClass.objects.filter(school=school, division=div, is_class_teacher=True)
                .select_related("teacher", "subject")
                .first()
            )
            div_label = (
                f"{div.SchoolClass.school_class} - Div {div.division}"
                if div.SchoolClass
                else f"Division {div.division}"
            )

            if not ct_assign or not ct_assign.teacher:
                missing_ct_divisions.append(div_label)
            else:
                ct_by_division[div.id] = ct_assign

            div_assignments = list(
                AssignClass.objects.filter(school=school, division=div)
                .exclude(teacher__isnull=True)
                .select_related("teacher", "subject")
            )
            assignments_by_division[div.id] = div_assignments

        if missing_ct_divisions:
            return Response(
                {
                    "error": "Cannot generate timetable. The following class divisions do not have a Class Teacher assigned:",
                    "missing_divisions": missing_ct_divisions,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if any division has NO assigned teachers at all
        empty_teacher_divisions = []
        for div in divisions:
            if not assignments_by_division.get(div.id):
                div_label = (
                    f"{div.SchoolClass.school_class} - Div {div.division}"
                    if div.SchoolClass
                    else f"Division {div.division}"
                )
                empty_teacher_divisions.append(div_label)

        if empty_teacher_divisions:
            return Response(
                {
                    "error": "Cannot generate timetable. The following class divisions have no teachers assigned:",
                    "missing_divisions": empty_teacher_divisions,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Parameters & Attendance Time Rule Fallback
        days_to_generate = request.data.get(
            "days", ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        )
        total_lectures = int(request.data.get("total_lecture", 6))
        include_break = request.data.get("include_break", True)
        if isinstance(include_break, str):
            include_break = include_break.lower() in ("true", "1", "yes")

        break_duration = int(request.data.get("break_duration", 20))
        break_after_lecture = int(request.data.get("break_after_lecture", max(1, total_lectures // 2)))

        start_time_str = request.data.get("start_time")
        end_time_str = request.data.get("end_time")

        if not start_time_str or not end_time_str:
            rule = AttendanceTimeRule.objects.filter(school=school).first()
            if not rule:
                loc = AttendanceLocation.objects.filter(school=school).first()
                if loc:
                    rule = loc.time_rule
            if rule and rule.start_time and rule.end_time:
                start_time_str = start_time_str or rule.start_time.strftime("%H:%M")
                end_time_str = end_time_str or rule.end_time.strftime("%H:%M")

        if not start_time_str:
            start_time_str = "07:00"
        if not end_time_str:
            end_time_str = "12:16"

        try:
            start_h, start_m = map(int, start_time_str.split(":")[:2])
            end_h, end_m = map(int, end_time_str.split(":")[:2])
        except Exception:
            start_h, start_m = 7, 0
            end_h, end_m = 12, 16

        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m
        total_working_minutes = end_minutes - start_minutes
        if total_working_minutes <= 0:
            total_working_minutes = 316

        if include_break:
            available_lecture_minutes = max(0, total_working_minutes - break_duration)
            lecture_duration = max(20, available_lecture_minutes // total_lectures)
        else:
            lecture_duration = max(20, total_working_minutes // total_lectures)

        # Build slot schedule configuration
        slot_configs = []
        lecture_count = 0
        total_slot_count = total_lectures + (1 if include_break else 0)

        for s_idx in range(1, total_slot_count + 1):
            if include_break and lecture_count == break_after_lecture and not any(sc.get("is_break") for sc in slot_configs):
                slot_configs.append({
                    "is_break": True,
                    "duration": break_duration,
                    "label": "Recess / Lunch Break"
                })
            else:
                lecture_count += 1
                slot_configs.append({
                    "is_break": False,
                    "lecture_num": lecture_count,
                    "duration": lecture_duration,
                })

        # Calculate exact start/end timestamps cumulatively
        curr_m = start_minutes
        for sc in slot_configs:
            sc["start_m"] = curr_m
            sc["end_m"] = min(end_minutes, curr_m + sc["duration"])
            curr_m = sc["end_m"]

        def format_minutes(m):
            return f"{m // 60:02d}:{m % 60:02d}"

        for sc in slot_configs:
            sc["start_str"] = format_minutes(sc["start_m"])
            sc["end_str"] = format_minutes(sc["end_m"])

        # 3. Schedule Generation Algorithm with Teacher Conflict Prevention
        draft_timetables = []
        booked_teachers = {
            day: {slot_num: set() for slot_num in range(1, total_slot_count + 1)}
            for day in days_to_generate
        }

        for day in days_to_generate:
            for div in divisions:
                div_id = div.id
                ct_assign = ct_by_division[div_id]
                ct_teacher = ct_assign.teacher
                ct_subject = ct_assign.subject

                all_div_assigns = assignments_by_division[div_id]

                slots_list = []

                for slot_num, sc in enumerate(slot_configs, start=1):
                    s_start = sc["start_str"]
                    s_end = sc["end_str"]

                    if sc["is_break"]:
                        slots_list.append({
                            "slot_number": slot_num,
                            "is_lecture": False,
                            "is_break": True,
                            "slot_start_time": s_start,
                            "slot_end_time": s_end,
                            "teacher": None,
                            "teacher_name": "Recess / Break",
                            "subject": None,
                            "subject_name": "Recess / Lunch Break",
                        })
                    else:
                        lec_num = sc["lecture_num"]
                        if lec_num == 1:
                            # RULE 1: Lecture 1 MUST be Class Teacher
                            chosen_teacher = ct_teacher
                            chosen_subject = ct_subject or (all_div_assigns[0].subject if all_div_assigns else None)
                            if chosen_teacher:
                                booked_teachers[day][slot_num].add(chosen_teacher.id)
                        else:
                            # RULE 2: Select non-conflicting teacher
                            available_assigns = [
                                a for a in all_div_assigns
                                if a.teacher_id not in booked_teachers[day][slot_num]
                            ]

                            if available_assigns:
                                chosen = random.choice(available_assigns)
                                chosen_teacher = chosen.teacher
                                chosen_subject = chosen.subject
                            else:
                                chosen = random.choice(all_div_assigns)
                                chosen_teacher = chosen.teacher
                                chosen_subject = chosen.subject

                            if chosen_teacher:
                                booked_teachers[day][slot_num].add(chosen_teacher.id)

                        slots_list.append({
                            "slot_number": slot_num,
                            "is_lecture": True,
                            "is_break": False,
                            "slot_start_time": s_start,
                            "slot_end_time": s_end,
                            "teacher": chosen_teacher.id if chosen_teacher else None,
                            "teacher_name": chosen_teacher.name if chosen_teacher else "",
                            "subject": chosen_subject.id if chosen_subject else None,
                            "subject_name": chosen_subject.name if chosen_subject else "",
                        })

                draft_timetables.append({
                    "class_division": div.id,
                    "class_name": div.SchoolClass.school_class if div.SchoolClass else "",
                    "division_name": div.division,
                    "day": day,
                    "total_lecture": len(slots_list),
                    "start_time": start_time_str,
                    "end_time": end_time_str,
                    "slots": slots_list,
                })

        return Response({
            "status": "preview",
            "message": "Draft timetable generated successfully for preview",
            "draft_timetables": draft_timetables,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-publish")
    def bulk_publish(self, request):
        school = request.user.school
        if not school:
            return Response(
                {"error": "User does not have a school assigned"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        timetables_data = request.data.get("timetables", [])
        if not timetables_data:
            return Response(
                {"error": "No timetables data provided for publishing"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            created_count = 0
            for tt_item in timetables_data:
                class_div_id = tt_item.get("class_division")
                day = tt_item.get("day")
                total_lecture = tt_item.get("total_lecture", 7)
                start_time = tt_item.get("start_time", "08:00")
                end_time = tt_item.get("end_time", "14:00")
                slots_data = tt_item.get("slots", [])

                Time_Table_tb.objects.filter(
                    school=school,
                    class_division_id=class_div_id,
                    day=day,
                ).delete()

                tt_instance = Time_Table_tb.objects.create(
                    school=school,
                    class_division_id=class_div_id,
                    day=day,
                    total_lecture=total_lecture,
                    start_time=start_time,
                    end_time=end_time,
                )

                for slot_item in slots_data:
                    Slot.objects.create(
                        school=school,
                        timetable=tt_instance,
                        slot_number=slot_item.get("slot_number"),
                        is_lecture=slot_item.get("is_lecture", True),
                        is_break=slot_item.get("is_break", False),
                        slot_start_time=slot_item.get("slot_start_time"),
                        slot_end_time=slot_item.get("slot_end_time"),
                        subject_id=slot_item.get("subject"),
                        teacher_id=slot_item.get("teacher"),
                    )

                created_count += 1

        return Response(
            {"message": f"Successfully published {created_count} timetable schedules!"},
            status=status.HTTP_201_CREATED,
        )


# ----------------------------------------------------------
# ATTENDANCE




class AttendanceStudentAPIView(APIView):

    def get(self, request):
        school = request.user.school
        teacher = getattr(request.user, "staff", None)

        if not teacher:
            return Response(
                {
                    "success": False,
                    "message": "Staff details not found for logged in user.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # GET ALL CLASS TEACHER ASSIGNMENTS FOR THIS TEACHER
        class_teacher_assignments = (
            AssignClass.objects.select_related("division", "division__SchoolClass")
            .filter(school=school, teacher=teacher, is_class_teacher=True)
        )

        # IF TEACHER NOT CLASS TEACHER
        if not class_teacher_assignments.exists():
            return Response(
                {
                    "success": False,
                    "message": "You are not assigned as class teacher.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_div_id = request.query_params.get("division_id")
        assign_class = None

        if requested_div_id:
            assign_class = class_teacher_assignments.filter(division_id=requested_div_id).first()

        if not assign_class:
            assign_class = class_teacher_assignments.first()

        div = assign_class.division

        # GET STUDENTS FOR THIS DIVISION ROBUSTLY
        students = Student.objects.filter(
            Q(school=school) & (
                Q(division=div) |
                Q(division=str(div.id)) |
                (Q(school_class=div.SchoolClass) & Q(division__iexact=div.division))
            )
        ).order_by("gr_no")

        serializer = StudentSerializer(students, many=True)

        assigned_divisions_data = [
            {
                "division_id": ac.division.id,
                "division_name": str(ac.division),
            }
            for ac in class_teacher_assignments
        ]

        return Response(
            {
                "success": True,
                "division_id": div.id,
                "division_name": str(div),
                "total_students": students.count(),
                "students": serializer.data,
                "assigned_divisions": assigned_divisions_data,
            }
        )


# views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import StudentAttendance




class StudentAttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        queryset = (
            StudentAttendance.objects
            .filter(school=request.user.school)
            .select_related(
                "student",
                "attendance_by",
            )
        )

        serializer = StudentAttendanceSerializer(
            queryset,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):
        student_id = request.data.get("student")
        today_date = timezone.now().date()

        existing_attendance = StudentAttendance.objects.filter(
            school=request.user.school,
            student_id=student_id,
            attendance_date=today_date
        ).first()

        if existing_attendance:
            serializer = StudentAttendanceSerializer(
                existing_attendance,
                data=request.data,
                context={"request": request},
                partial=True
            )
        else:
            serializer = StudentAttendanceSerializer(
                data=request.data,
                context={"request": request}
            )

        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()

        if attendance.is_present:
            status_text = "Present"
        elif attendance.is_absent:
            status_text = "Absent"
        else:
            status_text = "Not Marked"

        notification = StudentNotification.objects.create(
            school=attendance.school,
            student=attendance.student,
            created_by=request.user.staff,
            notification_type="ATTENDANCE",
            title="Attendance Marked" if not existing_attendance else "Attendance Updated",
            message=(
                f"Your child's attendance has been marked as "
                f"{status_text} on {attendance.attendance_date}"
            )
        )

        group_name = (
            f"school_{attendance.school_id}"
            f"_student_{attendance.student_id}"
            f"_attendance"
        )

        try:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "attendance_message",
                    "notification_id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                }
            )
        except Exception as e:
            print("Channel send notification error:", e)

        response_serializer = StudentAttendanceSerializer(attendance)

        return Response(
            response_serializer.data,
            status=status.HTTP_200_OK if existing_attendance else status.HTTP_201_CREATED
        )
    def put(self, request, id):
        attendance = get_object_or_404(
            StudentAttendance,
            id=id,
            school=request.user.school
        )

        serializer = StudentAttendanceSerializer(
            attendance,
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()

        if attendance.is_present:
            status_text = "Present"
        elif attendance.is_absent:
            status_text = "Absent"
        else:
            status_text = "Not Marked"

        notification = StudentNotification.objects.create(
            school=attendance.school,
            student=attendance.student,
            created_by=request.user.staff,
            notification_type="ATTENDANCE",
            title="Attendance Updated",
            message=(
                f"Your child's attendance has been updated to "
                f"{status_text} on {attendance.attendance_date}"
            )
        )

        group_name = (
            f"school_{attendance.school_id}"
            f"_student_{attendance.student_id}"
            f"_attendance"
        )

        channel_layer = get_channel_layer()

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "attendance_message",
                "notification_id": notification.id,
                "title": notification.title,
                "message": notification.message,
            }
        )

        return Response(serializer.data)
    def delete(self, request, id):
        attendance = get_object_or_404(
            StudentAttendance,
            id=id,
            school=request.user.school
        )

        attendance.delete()

        return Response(
            {"message": "Attendance deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
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
    serializer_class=HomeworkSerializer

    def get_student_division_name(self, student):
        # division_name = (student.division or "").strip()
        if not student.division:
            return ""
        return (student.division.division or "").strip()

        # if "(" in division_name and ")" in division_name:
        #     division_name = division_name.rsplit("(", 1)[-1].split(")", 1)[0].strip()

        return division_name

    # def get_serializer_class(self):
    #     """Return appropriate serializer based on action"""
    #     if self.action == "student_homework":
    #         return GetHomeworkSerializer
    #     elif self.action == "list" and self.is_student():
    #         return GetHomeworkSerializer
    #     return HomeworkSerializer

    def get_queryset(self):
        """Filter homework by school"""
        school = self.request.user.school
        
        queryset = Homework.objects.filter(school=school).select_related(
            "division", "teacher", "division__SchoolClass"
        )
        print("User:", self.request.user)
        
        


        # If user is a student, only show homework for their division
        # if self.is_student():
        #     try:
        #         student = self.request.user.student
        #         division_name = self.get_student_division_name(student)

        #         if not student.school_class_id or not division_name:
        #             return queryset.none()

        #         queryset = queryset.filter(
        #             division__SchoolClass_id=student.school_class_id,
        #             division__division__iexact=division_name,
        #             is_active=True,
        #         )
                
        #     except Student.DoesNotExist:
        #         queryset = queryset.none()
                
        if self.is_student():
            
            try:
                student = self.request.user.student
            except Student.DoesNotExist:
                return queryset.none()
            print("Student class:", student.school_class_id)
            print("Student division:", student.division_id)

            if not student.school_class_id or not student.division_id:
                return queryset.none()
            print(
                    list(
                        queryset.values(
                            "id",
                            "title",
                            "division_id",
                            "division__SchoolClass_id",
                            "is_active",
                        )
                    )
                )
            queryset = queryset.filter(
                division__SchoolClass_id=student.school_class_id,
                division_id=student.division_id,
                is_active=True,
            )

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

    @action(detail=False, methods=["get"], url_path=r"student[-_]homework")
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
        

        if not student.school_class_id:
            return Response(
                {"error": "Student class not assigned."},
                status=status.HTTP_400_BAD_REQUEST,
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

        submissions = homework.homeworksubmission_set.select_related("student", "checked_by")
        serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def division_details(self, request, pk=None):
        """Get division details for this homework"""
        homework = self.get_object()
        division = homework.division

        return Response(
            {
                "division_id": division.id,
                "division_name": division.division,
                "school_class": division.SchoolClass.school_class,
                "total_students": Student.objects.filter(
                    school_class=division.SchoolClass,
                    division=division.division,
                    school=request.user.school,
                ).count(),
                "submitted_count": homework.homeworksubmission_set.filter(
                    status__in=["submitted", "checked"]
                )
                .values("student")
                .distinct()
                .count(),
            }
        )


# class HomeworkSubmissionViewSet(ModelViewSet):
#     """
#     ViewSet for managing homework submissions.

#     Actions:
#     - CREATE: Students submit homework
#     - LIST: Get submissions (students see their own, teachers see all for their homework)
#     - RETRIEVE: Get submission details
#     - UPDATE: Update submission (teacher can grade)
#     - check-submission: Teacher grades the submission
#     """

#     permission_classes = [IsAuthenticated]
#     queryset = HomeworkSubmission.objects.all()
#     serializer_class = HomeworkSubmissionSerializer

#     def get_serializer_class(self):
#         """Return appropriate serializer based on action"""
#         if self.action == "check_submission":
#             return CheckHomeworkSubmissionSerializer
#         elif self.action == "retrieve":
#             return HomeworkSubmissionDetailSerializer
#         return HomeworkSubmissionSerializer

#     def get_queryset(self):
#         """Filter submissions based on user role"""
#         school = self.request.user.school
#         queryset = HomeworkSubmission.objects.filter(school=school).select_related(
#             "homework", "student", "checked_by"
#         )

#         # If user is a student, only show their own submissions
#         if self.is_student():
#             try:
#                 student = self.request.user.student
#                 queryset = queryset.filter(student=student)
#             except:
#                 queryset = queryset.none()

#         # If user is a teacher, only show submissions for their homework
#         elif self.is_teacher():
#             try:
#                 staff = self.request.user.staff
#                 queryset = queryset.filter(homework__teacher=staff)
#             except:
#                 queryset = queryset.none()

#         return queryset.order_by("-submitted_at", "-created_at")

#     def is_student(self):
#         """Check if logged-in user is a student"""
#         try:
#             return hasattr(self.request.user, "student")
#         except:
#             return False

#     def is_teacher(self):
#         """Check if logged-in user is a teacher"""
#         try:
#             return hasattr(self.request.user, "staff")
#         except:
#             return False

#     def create(self, request, *args, **kwargs):
#         """
#         Students submit homework.
#         Automatically sets the student to the logged-in user's student profile.
#         """
#         if not self.is_student():
#             return Response(
#                 {"error": "Only students can submit homework."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # Automatically set student from request user
#         try:
#             student = request.user.student
#         except Student.DoesNotExist:
#             return Response(
#                 {"error": "Student profile not found."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         # Add student to request data
#         request.data._mutable = True
#         request.data["student"] = student.id
#         request.data._mutable = False

#         return super().create(request, *args, **kwargs)

#     def update(self, request, *args, **kwargs):
#         """Teachers can only grade submissions (not modify student's submission)"""
#         submission = self.get_object()

#         if not self.is_teacher():
#             return Response(
#                 {"error": "Only teachers can grade submissions."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         if submission.homework.teacher.user != request.user:
#             return Response(
#                 {"error": "You can only grade submissions for your homework."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         # Only allow updating status, marks, and remarks
#         allowed_fields = {"status", "marks", "teacher_remark"}
#         provided_fields = set(request.data.keys())
#         invalid_fields = provided_fields - allowed_fields

#         if invalid_fields:
#             return Response(
#                 {"error": f"Cannot update fields: {', '.join(invalid_fields)}"},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         return super().update(request, *args, **kwargs)

#     def destroy(self, request, *args, **kwargs):
#         """Students can delete their own submissions, teachers cannot delete"""
#         submission = self.get_object()

#         if self.is_teacher():
#             return Response(
#                 {"error": "Teachers cannot delete submissions."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         if self.is_student():
#             try:
#                 student = request.user.student
#                 if submission.student != student:
#                     return Response(
#                         {"error": "You can only delete your own submissions."},
#                         status=status.HTTP_403_FORBIDDEN,
#                     )
#             except Student.DoesNotExist:
#                 pass

#         return super().destroy(request, *args, **kwargs)

#     @action(detail=True, methods=["post"])
#     def check_submission(self, request, pk=None):
#         """
#         Teacher grades a submission.
#         Endpoint to mark a submission as checked with marks and remarks.
#         """
#         submission = self.get_object()

#         if not self.is_teacher():
#             return Response(
#                 {"error": "Only teachers can grade submissions."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         if submission.homework.teacher.user != request.user:
#             return Response(
#                 {"error": "You can only grade submissions for your homework."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         serializer = self.get_serializer(submission, data=request.data, partial=True)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_200_OK)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     @action(detail=False, methods=["get"])
#     def pending_submissions(self, request):
#         """Get all pending submissions for the teacher"""
#         if not self.is_teacher():
#             return Response(
#                 {"error": "Only teachers can access this endpoint."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         try:
#             staff = request.user.staff
#         except:
#             return Response(
#                 {"error": "Staff profile not found."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         submissions = self.get_queryset().filter(status__in=["pending", "submitted"])
#         serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
#         return Response(serializer.data)

#     @action(detail=False, methods=["get"])
#     def my_submissions(self, request):
#         """Get all submissions from the logged-in student"""
#         if not self.is_student():
#             return Response(
#                 {"error": "Only students can access this endpoint."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         try:
#             student = request.user.student
#         except:
#             return Response(
#                 {"error": "Student profile not found."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         submissions = self.get_queryset().filter(student=student)
#         serializer = HomeworkSubmissionDetailSerializer(submissions, many=True)
#         return Response(serializer.data)

#     @action(detail=False, methods=["get"])
#     def submission_stats(self, request, **kwargs):
#         """Get submission statistics for a homework"""
#         homework_id = request.query_params.get("homework_id")

#         if not homework_id:
#             return Response(
#                 {"error": "homework_id query parameter is required."},
#                 status=status.HTTP_400_BAD_REQUEST,
#             )

#         try:
#             homework = Homework.objects.get(id=homework_id, school=request.user.school)
#         except Homework.DoesNotExist:
#             return Response(
#                 {"error": "Homework not found."},
#                 status=status.HTTP_404_NOT_FOUND,
#             )

#         if homework.teacher.user != request.user:
#             return Response(
#                 {"error": "You can only view stats for your homework."},
#                 status=status.HTTP_403_FORBIDDEN,
#             )

#         submissions = homework.homeworksubmission_set.all()
#         total_students = Student.objects.filter(
#             school_class=homework.division.SchoolClass,
#             division=homework.division.division,
#             school=request.user.school,
#         ).count()

#         return Response(
#             {
#                 "homework_id": homework.id,
#                 "homework_title": homework.title,
#                 "total_students": total_students,
#                 "submitted": submissions.filter(
#                     status__in=["submitted", "checked"]
#                 ).count(),
#                 "pending": submissions.filter(status="pending").count(),
#                 "late": submissions.filter(status="late").count(),
#                 "checked": submissions.filter(status="checked").count(),
#                 "average_marks": submissions.filter(marks__isnull=False).aggregate(
#                     avg=models.Avg("marks")
#                 )["avg"]
#                 or 0,
#             }
#         )


# ------------------------------------GET STUDENT ----------------------------




class StudentGetView(ModelViewSet):

    queryset = Student.objects.all()

    serializer_class = StudentGetSerializer

    def get_queryset(self):
        return Student.objects.filter(school=self.request.user.school)



class StudentDocumentView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            user = self.request.user

            if hasattr(user, "staff"):
                return [IsAuthenticated(), Isteacher()]

            if hasattr(user, "student"):
                return [IsAuthenticated(), Isstudent()]

            if hasattr(user, "perents"):   
                return [IsAuthenticated(), Isparent()]

            return [IsAuthenticated()]

        return [IsAuthenticated(), Isteacher()]

    def get(self, request):

        user = request.user

    # Teacher → See all student documents of the school
        if hasattr(user, "staff"):
            student_documents = StudentDocument.objects.filter(
                school=user.school
            )

        # Student → See only their own documents
        elif hasattr(user, "student"):
            student_documents = StudentDocument.objects.filter(
                student=user.student
            )

        # Parent → See documents of their child/children
        elif hasattr(user, "perents"):
            parent = user.perents

            student_documents = StudentDocument.objects.filter(
                student__parent=parent
            )

        else:
            return Response(
                {"error": "Invalid user role."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = StudentDocumentSerializer(
            student_documents,
            many=True
        )

        return Response(serializer.data)
    
    def post(self,request):
        serializer=StudentDocumentSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(school=request.user.school,uploaded_by=request.user.staff)
            return Response(serializer.data)
        return Response(serializer.errors,status=404)
    
    def put(self, request, id):
        student_document = get_object_or_404(
            StudentDocument,
            id=id,
            school=request.user.school
        )

        serializer = StudentDocumentSerializer(
            student_document,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, id):
        student_document = get_object_or_404(
            StudentDocument,
            id=id,
            school=request.user.school
        )

        student_document.delete()

        return Response(
            {"message": "Student document deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )
    


class StudentListView(APIView):
    permission_classes = [IsAuthenticated, Isteacher]

    def get(self, request):
        assign = (
            AssignClass.objects.select_related("division", "division__SchoolClass")
            .filter(
                teacher=request.user.staff,
                school=request.user.school,
                is_class_teacher=True
            )
            .first()
        )
        if not assign:
            return Response(
                {"error": "You are not assigned as a class teacher."},
                status=status.HTTP_404_NOT_FOUND
            )

        div = assign.division
        students = Student.objects.filter(
            Q(school=request.user.school) & (
                Q(division=div) |
                Q(division=str(div.id)) |
                (Q(school_class=div.SchoolClass) & Q(division__iexact=div.division))
            )
        ).values(
            "id",
            "name",
            "surname",
            "gr_no"
        )

        return Response(students)





class StudentNotificationView(APIView):

    def get_permissions(self):

        if self.request.method == "GET":
            return [IsAuthenticated(), Isparent()]

        return [IsAuthenticated(), Isteacher()]

    def get(self, request):

        student_ids = (
            Perents.objects.filter(
                user=request.user
            )
            .values_list(
                "perents_of_id",
                flat=True
            )
        )

        notifications = (
            StudentNotification.objects.filter(
                student_id__in=student_ids
            )
            .order_by("-created_at")
        )

        serializer = StudentNotificationSerializer(
            notifications,
            many=True
        )

        return Response(serializer.data)



class TeacherClassesView(APIView):
    permission_classes = [IsAuthenticated, Isteacher]

    def get(self, request):
        assignments = (
            AssignClass.objects.filter(
                school=request.user.school,
                teacher=request.user.staff
            )
            .select_related("division__SchoolClass")
        )

        data = []
        added_classes = set()

        for assignment in assignments:
            school_class = assignment.division.SchoolClass

            # Avoid duplicate classes
            if school_class.id not in added_classes:
                added_classes.add(school_class.id)

                data.append({
                    "class_id": school_class.id,
                    "class_name": school_class.school_class,
                })

        return Response(data)


class ExamView(APIView):

    def get_permissions(self):
        if self.request.method == "GET":
            if self.request.user.groups.filter(name="PARENT").exists():
                return [IsAuthenticated(), Isparent()]
            elif self.request.user.groups.filter(name="TEACHER").exists():
                return [IsAuthenticated(), Isteacher()]
            return [IsAuthenticated()]

        return [IsAuthenticated(), Isteacher()]


    def get(self, request):
        if hasattr(request.user, "staff"):
            # Teacher: show exams created by this teacher
            exams = Exam.objects.filter(
                created_by=request.user.staff
            ).order_by("-created_at")

            serializer = ExamSerializer(exams, many=True)
            return Response(serializer.data)

        # Parent
        student_ids = (
            Perents.objects.filter(user=request.user)
            .values_list("perents_of_id", flat=True)
        )

        class_ids = (
            Student.objects.filter(id__in=student_ids)
            .values_list("school_class_id", flat=True)
        )

        notifications = (
            ExamNotification.objects.filter(
                exam__class_group_id__in=class_ids
            )
            .select_related("exam")
            .order_by("-created_at")
        )

        serializer = ExamNotificationSerializer(
            notifications,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):

        serializer = ExamSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        exam = serializer.save(
            school=request.user.school,
            created_by=request.user.staff,
        )

        notification = ExamNotification.objects.create(
            exam=exam,
            title=f"New Exam: {exam.title}",
            message=(
                f"Exam scheduled on {exam.exam_date} "
                f"from {exam.start_time} to {exam.end_time}"
            )
        )

        channel_layer = get_channel_layer()

        group_name = (
    f"school_{exam.school_id}_class_{exam.class_group_id}_parents"
)

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                "type": "send_notification",
                "notification_id": notification.id,
                "title": notification.title,
                "message": notification.message,
            }
        )

        return Response(
            ExamSerializer(exam).data,
            status=status.HTTP_201_CREATED
        )
    
    def put(self, request, id):
        try:
            exam = Exam.objects.get(
                id=id,
                school=request.user.school
            )
        except Exam.DoesNotExist:
            return Response(
                {"error": "Exam not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ExamSerializer(
            exam,
            data=request.data
        )

        if serializer.is_valid():
            serializer.save()

            # Update notification if it exists
            notification = ExamNotification.objects.filter(
                exam=exam
            ).first()

            if notification:
                notification.title = f"Updated Exam: {exam.title}"
                notification.message = (
                    f"Exam scheduled on {exam.exam_date} "
                    f"from {exam.start_time} to {exam.end_time}"
                )
                notification.save()

            return Response(serializer.data)

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )


    def delete(self, request, id):
        try:
            exam = Exam.objects.get(
                id=id,
                school=request.user.school
            )
        except Exam.DoesNotExist:
            return Response(
                {"error": "Exam not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        exam.delete()

        return Response(
            {"message": "Exam deleted successfully"},
            status=status.HTTP_204_NO_CONTENT
        )



class HomeworkSubmissionViewSet(ModelViewSet):
    serializer_class = HomeworkSubmissionSerializer
    queryset = HomeworkSubmissions.objects.all()
    permission_classes = []



    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            user = self.request.user

            if hasattr(user, "staff"):
                return [Isteacher()]

            if hasattr(user, "student"):
                return [Isstudent()]

            return [IsAuthenticated()]

        return [Isstudent()]

    def get_queryset(self):
    # Student: only their own submissions
        if hasattr(self.request.user, "student"):
            return HomeworkSubmissions.objects.filter(
                student=self.request.user.student
            )

        # Teacher: all submissions for homework created by them
        elif hasattr(self.request.user, "staff"):
            return HomeworkSubmissions.objects.filter(
                homework__teacher=self.request.user.staff,
                homework__school=self.request.user.school
            )

        return HomeworkSubmissions.objects.none()

    def perform_create(self, serializer):
        serializer.save(
            student=self.request.user.student
        )
    


class MonthlyProgressReportView(APIView):
    permission_classes = [Isteacher]


    def get(self, request, id=None):

        if id:
            report = get_object_or_404(
                MonthlyProgressReport,
                id=id,
                school=request.user.school,
                created_by=request.user.staff
            )

            serializer = MonthlyProgressReportSerializer(report)
            return Response(serializer.data)

        reports = MonthlyProgressReport.objects.filter(
            school=request.user.school,
            created_by=request.user.staff
        ).order_by("-created_at")

        serializer = MonthlyProgressReportSerializer(
            reports,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):
        
        serializer = MonthlyProgressReportSerializer(
            data=request.data
        )

        if serializer.is_valid():
            student = serializer.validated_data["student"]

            # Check if logged-in teacher is the class teacher
            div = student.division
            if isinstance(div, Division):
                is_class_teacher = AssignClass.objects.filter(
                    school=request.user.school,
                    teacher=request.user.staff,
                    division=div,
                    is_class_teacher=True
                ).exists()
            else:
                is_class_teacher = AssignClass.objects.filter(
                    school=request.user.school,
                    teacher=request.user.staff,
                    division__SchoolClass=student.school_class,
                    division__division__iexact=str(div or ""),
                    is_class_teacher=True
                ).exists()

            if not is_class_teacher:
                return Response(
                    {
                        "error": "Only the class teacher of this student's division can create a monthly progress report."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

            report = serializer.save(
                school=request.user.school,
                created_by=request.user.staff
            )

            data = MonthlyProgressReportSerializer(report).data

            channel_layer = get_channel_layer()

            group_name = progress_group(
                report.school.id,
                report.student.id
            )

            async_to_sync(
                channel_layer.group_send
            )(
                group_name,
                {
                    "type": "progressreport_message",
                    "student": report.student.id,
                    "month": report.month,
                    "year": report.year,
                    "attendance_percentage": round(
                        float(report.attendance_percentage), 2
                    ),
                    "overall_score": round(
                        float(report.overall_score), 2
                    ),
                    "grade": data["grade"],
                    "discipline": report.discipline,
                    "communication_skills": report.communication_skills,
                    "emotional_development": report.emotional_development,
                    "social_development": report.social_development,
                    "freindly_with_others": report.freindly_with_others,
                    "remark": report.remark,
                }
            )

            return Response(
                serializer.data,
                status=status.HTTP_201_CREATED
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    
    def put(self, request, id):
        report = get_object_or_404(
            MonthlyProgressReport,
            id=id,
            school=request.user.school,
            created_by=request.user.staff
        )

        serializer = MonthlyProgressReportSerializer(
            report,
            data=request.data
        )

        if serializer.is_valid():
            report = serializer.save()

            data = MonthlyProgressReportSerializer(report).data

            channel_layer = get_channel_layer()

            async_to_sync(channel_layer.group_send)(
                progress_group(
                    report.school.id,
                    report.student.id
                ),
                {
                    "type": "progressreport_message",
                    "student": report.student.id,
                    "month": report.month,
                    "year": report.year,
                    "attendance_percentage": round(
                        float(report.attendance_percentage), 2
                    ),
                    "overall_score": round(
                        float(report.overall_score), 2
                    ),
                    "grade": data["grade"],
                    "discipline": report.discipline,
                    "communication_skills": report.communication_skills,
                    "emotional_development": report.emotional_development,
                    "social_development": report.social_development,
                    "freindly_with_others": report.freindly_with_others,
                    "remark": report.remark,
                }
            )

            return Response(
                serializer.data,
                status=status.HTTP_200_OK
            )

        return Response(
            serializer.errors,
            status=status.HTTP_400_BAD_REQUEST
        )
    def delete(self, request, id):
        report = get_object_or_404(
            MonthlyProgressReport,
            id=id,
            school=request.user.school,
            created_by=request.user.staff
        )

        report.delete()

        return Response(
            {"message": "Progress report deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )




class TeacherAssignmentView(APIView):
    permission_classes = [Isteacher]

    def get(self, request):
        assignments = AssignClass.objects.filter(
            school=request.user.school,
            teacher=request.user.staff
        ).select_related(
            "subject",
            "division",
            "division__SchoolClass"
        )

        data = []

        for assignment in assignments:
            data.append({
                "subject_id": assignment.subject.id,
                "subject_name": assignment.subject.name,
                "student_class": assignment.division.id,   # or SchoolClass.id depending on your StudyMaterial model
                "class_name": assignment.division.SchoolClass.school_class,
                "division": assignment.division.division,
            })

        return Response(data)


class StudyMaterialView(APIView):
    permission_classes = [Isteacher]
    def get(self, request):
        materials = StudyMaterial.objects.filter(
            school=request.user.school,
            staff=request.user.staff
        ).order_by("-created_at")

        serializer = StudyMaterialSerializer(
            materials,
            many=True,
            context={"request": request}
        )

        return Response(serializer.data)

    def post(self, request):
        school = request.user.school
        staff = request.user.staff

        serializer = StudyMaterialSerializer(data=request.data)

        if serializer.is_valid():
            material = serializer.save(school=school, staff=staff)

            channel_layer = get_channel_layer()

            
            group_name = f"student_{material.school.id}_class_{material.student_class.id}"

            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    "type": "studymaterial",

                    "subject": str(material.subject),
                    "student_class": str(material.student_class),
                    "material_type": material.material_type,
                    "title": material.title,
                    "description": material.description,

                    # ✅ always send URL, not file object
                    "file": request.build_absolute_uri(material.file.url),
                }
            )

            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)
    def put(self, request, id):
        material = get_object_or_404(
            StudyMaterial,
            id=id,
            school=request.user.school,
            staff=request.user.staff
        )

        serializer = StudyMaterialSerializer(
            material,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    def delete(self, request, id):
        material = get_object_or_404(
            StudyMaterial,
            id=id,
            school=request.user.school,
            staff=request.user.staff
        )

        material.delete()

        return Response(
            {"message": "Study material deleted successfully."},
            status=204
        )

    


