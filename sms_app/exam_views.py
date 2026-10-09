import math
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from sms_app.models import (
    School,
    AcademicYear,
    Student,
    Staff,
    SchoolClass,
    Division,
    Subject,
    AssignClass,
    ResultWeightageConfig,
    ResultWeightageComponent,
    ExamRoom,
    ExamTerm,
    Exam,
    SeatingAllocation,
    Result,
    TeacherAssessmentScore,
    ClassTeacherMarksVerification,
    FinalStudentResult,
    ResultAuditLog,
)

from sms_app.exam_serializers import (
    ResultWeightageConfigSerializer,
    ResultWeightageComponentSerializer,
    ExamRoomSerializer,
    ExamTermSerializer,
    ExamFullSerializer,
    SeatingAllocationSerializer,
    SubjectMarksEntrySerializer,
    TeacherAssessmentScoreSerializer,
    ClassTeacherMarksVerificationSerializer,
    FinalStudentResultSerializer,
)

from sms_app.result_engine import ResultCalculationEngine
from sms_app.permissions import IsCLerk  # or principal/teacher check


def check_is_class_teacher(user, school_class, division=None):
    if not user or not hasattr(user, "staff") or not user.staff:
        return False
    staff = user.staff
    qs = AssignClass.objects.filter(
        school=user.school,
        teacher=staff,
        is_class_teacher=True
    )
    if school_class:
        if isinstance(school_class, (int, str)) and str(school_class).isdigit():
            qs = qs.filter(division__SchoolClass_id=int(school_class))
        elif hasattr(school_class, "id"):
            qs = qs.filter(division__SchoolClass_id=school_class.id)
    if division and str(division).strip().upper() not in ["", "ALL"]:
        div_clean = str(division).replace("Div", "").replace("div", "").strip(" ()")
        qs = qs.filter(Q(division__division__iexact=division) | Q(division__division__iexact=div_clean))
    return qs.exists()


def check_is_admin_or_clerk(user):
    if not user:
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    user_role = str(getattr(user, "role", "") or "").strip().upper()
    if user_role in ["PRINCIPAL", "CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "ADMIN", "SUPERADMIN", "ADMIN(TRUSTEE)", "TRUSTEE", "SUPER_ADMIN"]:
        return True
    staff = getattr(user, "staff", None)
    if staff:
        staff_cat = str(getattr(staff, "category", "") or "").strip().upper()
        if staff_cat in ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "PRINCIPAL", "ADMIN", "TRUSTEE"]:
            return True
    user_groups = [str(g).strip().upper() for g in user.groups.values_list("name", flat=True)]
    if any(r in user_groups for r in ["PRINCIPAL", "CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "ADMIN(TRUSTEE)", "ADMIN", "TRUSTEE", "SUPERADMIN", "SUPER_ADMIN"]):
        return True
    return False



class ResultWeightageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ResultWeightageConfigSerializer

    def get_queryset(self):
        school = self.request.user.school
        qs = ResultWeightageConfig.objects.filter(school=school)
        year_id = self.request.query_params.get("academic_year")
        if year_id:
            qs = qs.filter(academic_year_id=year_id)
        class_id = self.request.query_params.get("school_class")
        if class_id is not None and str(class_id).strip() != "":
            if str(class_id).lower() in ["null", "none", "global", "all"]:
                qs = qs.filter(school_class__isnull=True)
            else:
                qs = qs.filter(school_class_id=class_id)
        return qs

    def create(self, request, *args, **kwargs):
        school = request.user.school
        academic_year_id = request.data.get("academic_year")
        school_class_id = request.data.get("school_class")
        if school_class_id in ["null", "none", "global", "ALL", "", None]:
            school_class_id = None
        title = request.data.get("title", "Academic Year Dynamic Weightage")

        if not academic_year_id:
            return Response({"error": "academic_year is required"}, status=status.HTTP_400_BAD_REQUEST)

        config, created = ResultWeightageConfig.objects.get_or_create(
            school=school,
            academic_year_id=academic_year_id,
            school_class_id=school_class_id,
            defaults={"title": title}
        )

        if not created and title:
            config.title = title
            config.save()

        serializer = self.get_serializer(config)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="save-components")
    def save_components(self, request, pk=None):
        config = self.get_object()
        if config.is_locked:
            return Response(
                {"error": "This Result Weightage Configuration is locked and cannot be edited."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        components_data = request.data.get("components", [])
        if not isinstance(components_data, list):
            return Response({"error": "components must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate total weightage sum
        total_sum = sum([float(c.get("weightage_percentage", 0)) for c in components_data])

        with transaction.atomic():
            # Clear existing components and replace with new dynamic list
            config.components.all().delete()
            for idx, c in enumerate(components_data):
                ResultWeightageComponent.objects.create(
                    config=config,
                    name=c.get("name", f"Component {idx+1}"),
                    component_type=c.get("component_type", "EXAM"),
                    weightage_percentage=Decimal(str(c.get("weightage_percentage", 0))),
                    sequence=idx + 1,
                )

            # Auto-activate if sum is 100%
            if abs(total_sum - 100.0) < 0.01:
                config.status = "ACTIVE"
                config.is_active = True
            else:
                config.status = "DRAFT"
                config.is_active = False

            config.save()

        return Response(
            {
                "message": f"Successfully updated weightage components. Total sum: {total_sum}%",
                "total_weightage": total_sum,
                "is_valid": abs(total_sum - 100.0) < 0.01,
                "config": ResultWeightageConfigSerializer(config).data,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="toggle-lock")
    def toggle_lock(self, request, pk=None):
        config = self.get_object()
        config.is_locked = not config.is_locked
        if config.is_locked:
            config.status = "LOCKED"
        else:
            config.status = "ACTIVE" if config.is_active else "DRAFT"
        config.save()
        return Response({"message": f"Configuration is now {'LOCKED' if config.is_locked else 'UNLOCKED'}.", "is_locked": config.is_locked})


class ExamRoomViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExamRoomSerializer

    def get_queryset(self):
        return ExamRoom.objects.filter(school=self.request.user.school)

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)

    def create(self, request, *args, **kwargs):
        room_number = request.data.get("room_number", "").strip()
        if room_number and ExamRoom.objects.filter(school=request.user.school, room_number=room_number).exists():
            return Response(
                {"error": f"Exam Room '{room_number}' already exists. Please use a different room number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)


class ExamTermViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExamTermSerializer

    def get_queryset(self):
        qs = ExamTerm.objects.filter(school=self.request.user.school)
        year_id = self.request.query_params.get("academic_year")
        if year_id:
            qs = qs.filter(academic_year_id=year_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


class ExamFullViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ExamFullSerializer

    def get_queryset(self):
        qs = Exam.objects.filter(school=self.request.user.school)
        
        user = self.request.user
        user_groups = [str(g).strip().upper() for g in user.groups.values_list('name', flat=True)] if user else []
        user_role = str(getattr(user, "role", "") or "").strip().upper()
        staff = getattr(user, "staff", None)
        staff_cat = str(getattr(staff, "category", "") or "").strip().upper() if staff else ""

        is_admin_or_clerk = (
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or user_role in ["PRINCIPAL", "CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "ADMIN", "SUPERADMIN", "ADMIN(TRUSTEE)", "TRUSTEE", "SUPER_ADMIN"]
            or staff_cat in ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "PRINCIPAL", "ADMIN", "TRUSTEE"]
            or any(r in user_groups for r in ["PRINCIPAL", "CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "ADMIN(TRUSTEE)", "ADMIN", "TRUSTEE", "SUPERADMIN", "SUPER_ADMIN"])
        )
        
        if not is_admin_or_clerk:
            if staff:
                from .models import AssignClass
                assigned_subjects = AssignClass.objects.filter(teacher=staff).values_list('subject_id', flat=True)
                qs = qs.filter(subject_id__in=assigned_subjects)

        if getattr(self, "action", None) in ["retrieve", "update", "partial_update", "destroy"]:
            return qs

        year_id = self.request.query_params.get("academic_year")
        term_id = self.request.query_params.get("exam_term")
        class_id = self.request.query_params.get("class_group")
        div = self.request.query_params.get("division")

        if year_id: qs = qs.filter(academic_year_id=year_id)
        if term_id: qs = qs.filter(exam_term_id=term_id)
        if class_id: qs = qs.filter(class_group_id=class_id)
        if div: qs = qs.filter(division=div)

        return qs.order_by("exam_date", "start_time")

    def perform_create(self, serializer):
        staff = getattr(self.request.user, "staff", None)
        if not staff:
            staff = Staff.objects.filter(school=self.request.user.school).first()
        serializer.save(school=self.request.user.school, created_by=staff)

    def create(self, request, *args, **kwargs):
        school = request.user.school
        staff = getattr(request.user, "staff", None) or Staff.objects.filter(school=school).first()

        data = request.data.copy()
        division = data.get("division", "") or ""
        class_group_id = data.get("class_group")
        exam_date = data.get("exam_date")
        start_time = data.get("start_time")
        end_time = data.get("end_time")

        subject_id = data.get("subject")
        title = data.get("title", "").strip()

        # 1. Timetable Clash Validation Helper: Same Class, Same Date, Overlapping Time Slot
        parsed_date = exam_date
        if isinstance(exam_date, str) and "-" in exam_date:
            parts = exam_date.split("-")
            if len(parts[0]) == 2 and len(parts[2]) == 4:  # DD-MM-YYYY -> YYYY-MM-DD
                parsed_date = f"{parts[2]}-{parts[1]}-{parts[0]}"

        parsed_start = start_time
        if isinstance(start_time, str) and len(start_time) == 5:
            parsed_start = f"{start_time}:00"

        parsed_end = end_time
        if isinstance(end_time, str) and len(end_time) == 5:
            parsed_end = f"{end_time}:00"

        data["exam_date"] = parsed_date
        data["start_time"] = parsed_start
        data["end_time"] = parsed_end

        def find_clash(target_div):
            clash_qs = Exam.objects.filter(
                school=school,
                class_group_id=class_group_id,
                exam_date=parsed_date,
                start_time__lt=parsed_end,
                end_time__gt=parsed_start,
            )
            if target_div and target_div != "ALL":
                clash_qs = clash_qs.filter(
                    Q(division__isnull=True) | Q(division="") | Q(division="ALL") | Q(division=target_div)
                )
            return clash_qs.select_related("subject", "class_group").first()

        # 2. Duplicate Subject Check Helper: A subject paper can ONLY be scheduled once per term per division
        def find_subject_duplicate(target_div):
            if not subject_id or not title:
                return None
            dup_qs = Exam.objects.filter(
                school=school,
                class_group_id=class_group_id,
                subject_id=subject_id,
                title__iexact=title,
            )
            if target_div and target_div != "ALL":
                dup_qs = dup_qs.filter(
                    Q(division__isnull=True) | Q(division="") | Q(division="ALL") | Q(division=target_div)
                )
            return dup_qs.select_related("subject", "class_group").first()

        # If creating for "ALL" divisions or empty division:
        if (not division or division == "ALL") and class_group_id:
            active_divs = list(
                Division.objects.filter(school=school, SchoolClass_id=class_group_id)
                .values_list("division", flat=True)
                .distinct()
            )
            if active_divs:
                # Check duplicate subject & clashes for all active divisions first
                for div_letter in active_divs:
                    dup_exam = find_subject_duplicate(div_letter)
                    if dup_exam:
                        cls_name = dup_exam.class_group.school_class if dup_exam.class_group else "this class"
                        sub_name = dup_exam.subject.name if dup_exam.subject else "this subject"
                        return Response(
                            {
                                "error": f"Duplicate Subject Paper Error: {sub_name} paper is already scheduled for {dup_exam.title} in {cls_name} (Div {div_letter}) on {dup_exam.exam_date}. A subject paper can only be scheduled once per exam term per division."
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    clashing_exam = find_clash(div_letter)
                    if clashing_exam:
                        cls_name = clashing_exam.class_group.school_class if clashing_exam.class_group else "this class"
                        sub_name = clashing_exam.subject.name if clashing_exam.subject else "another subject"
                        return Response(
                            {
                                "error": f"Exam Timetable Clash: {cls_name} (Div {div_letter}) already has an exam paper ({sub_name}) scheduled on {exam_date} between {clashing_exam.start_time} and {clashing_exam.end_time}. Same class cannot have two subject exams at the same time."
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                created_exams = []
                for div_letter in active_divs:
                    div_data = data.copy()
                    div_data["division"] = div_letter
                    serializer = self.get_serializer(data=div_data)
                    serializer.is_valid(raise_exception=True)
                    exam_obj = serializer.save(school=school, created_by=staff)
                    created_exams.append(self.get_serializer(exam_obj).data)
                return Response(created_exams, status=status.HTTP_201_CREATED)

        # Single Division Exam Creation:
        dup_exam = find_subject_duplicate(division)
        if dup_exam:
            cls_name = dup_exam.class_group.school_class if dup_exam.class_group else "this class"
            sub_name = dup_exam.subject.name if dup_exam.subject else "this subject"
            div_str = f" (Div {division})" if division else ""
            return Response(
                {
                    "error": f"Duplicate Subject Paper Error: {sub_name} paper is already scheduled for {dup_exam.title} in {cls_name}{div_str} on {dup_exam.exam_date}. A subject paper can only be scheduled once per exam term per division."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        clashing_exam = find_clash(division)
        if clashing_exam:
            cls_name = clashing_exam.class_group.school_class if clashing_exam.class_group else "this class"
            sub_name = clashing_exam.subject.name if clashing_exam.subject else "another subject"
            div_str = f" (Div {division})" if division else ""
            return Response(
                {
                    "error": f"Exam Timetable Clash: {cls_name}{div_str} already has an exam paper ({sub_name}) scheduled on {exam_date} between {clashing_exam.start_time} and {clashing_exam.end_time}. Same class cannot have two subject exams at the same time."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        exam_obj = serializer.save(school=school, created_by=staff)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="publish-timetable")
    def publish_timetable(self, request):
        academic_year = request.data.get("academic_year")
        term_id = request.data.get("exam_term")
        class_id = request.data.get("class_group")
        division = request.data.get("division")
        action_type = request.data.get("action", "PUBLISH")  # PUBLISH or DRAFT

        qs = Exam.objects.filter(school=request.user.school)
        if academic_year: qs = qs.filter(academic_year_id=academic_year)
        if term_id: qs = qs.filter(exam_term_id=term_id)
        if class_id: qs = qs.filter(class_group_id=class_id)
        if division and division != "ALL": qs = qs.filter(division=division)

        new_status = "PUBLISHED" if action_type == "PUBLISH" else "DRAFT"
        updated_count = qs.update(status=new_status)

        return Response({
            "message": f"Successfully updated timetable status to '{new_status}' for {updated_count} exam paper(s).",
            "count": updated_count,
            "status": new_status,
        })

    @action(detail=False, methods=["get"], url_path="timetable-grid")
    def timetable_grid(self, request):
        academic_year = request.query_params.get("academic_year")
        term_id = request.query_params.get("exam_term")
        class_id = request.query_params.get("class_group")
        division = request.query_params.get("division")

        qs = Exam.objects.filter(school=request.user.school).select_related(
            "subject", "class_group", "room", "exam_term"
        ).order_by("exam_date", "start_time")

        if academic_year: qs = qs.filter(academic_year_id=academic_year)
        if term_id: qs = qs.filter(exam_term_id=term_id)
        if class_id: qs = qs.filter(class_group_id=class_id)
        if division and division != "ALL": qs = qs.filter(division=division)

        # Build timetable rows
        timetable_data = []
        for ex in qs:
            timetable_data.append({
                "id": ex.id,
                "date": str(ex.exam_date),
                "day": ex.exam_date.strftime("%A") if ex.exam_date else "",
                "start_time": str(ex.start_time)[:5] if ex.start_time else "",
                "end_time": str(ex.end_time)[:5] if ex.end_time else "",
                "duration_minutes": ex.duration_minutes,
                "class_name": ex.class_group.school_class if ex.class_group else "",
                "division": ex.division or "ALL",
                "subject_name": ex.subject.name if ex.subject else "",
                "subject_id": ex.subject_id,
                "room_number": ex.room.room_number if ex.room else "TBA",
                "max_marks": float(ex.max_marks),
                "passing_marks": float(ex.passing_marks),
                "status": ex.status,
                "term_name": ex.exam_term.name if ex.exam_term else ex.title,
            })

        return Response({
            "exams": timetable_data,
            "total_papers": len(timetable_data),
            "is_all_published": all(e["status"] == "PUBLISHED" for e in timetable_data) if timetable_data else False,
        })


class SeatingAllocationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SeatingAllocationSerializer

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, "school", None)
        if not school:
            return SeatingAllocation.objects.none()

        qs = SeatingAllocation.objects.filter(exam__school=school).select_related(
            "exam", "exam__subject", "exam__class_group", "room", "student"
        )
        
        exam_id = self.request.query_params.get("exam")
        if exam_id:
            qs = qs.filter(exam_id=exam_id)
            
        academic_year = self.request.query_params.get("academic_year")
        title = self.request.query_params.get("title")
        if academic_year:
            qs = qs.filter(exam__academic_year_id=academic_year)
        if title and str(title).strip().upper() != "ALL":
            qs = qs.filter(Q(exam__title__iexact=str(title).strip()) | Q(exam__title__icontains=str(title).strip()))
            
        room_id = self.request.query_params.get("room")
        if room_id:
            qs = qs.filter(room_id=room_id)

        school_class = self.request.query_params.get("school_class") or self.request.query_params.get("class_id")
        if school_class and str(school_class).strip().upper() != "ALL":
            if str(school_class).isdigit():
                qs = qs.filter(Q(exam__class_group_id=int(school_class)) | Q(student__school_class_id=int(school_class)))
            else:
                qs = qs.filter(Q(exam__class_group__school_class__iexact=str(school_class).strip()) | Q(student__school_class__school_class__iexact=str(school_class).strip()))

        division = self.request.query_params.get("division")
        if division and str(division).strip().upper() != "ALL":
            div_val = str(division).strip()
            if div_val.lower().startswith("div "):
                div_val = div_val[4:].strip()
            elif div_val.lower().startswith("div"):
                div_val = div_val[3:].strip()
            qs = qs.filter(
                Q(exam__division__iexact=div_val) | Q(student__division__iexact=div_val) |
                Q(exam__division__iexact=f"Div {div_val}") | Q(student__division__iexact=f"Div {div_val}") |
                Q(student__division__isnull=True) | Q(student__division="")
            )

        return qs

    @action(detail=False, methods=["post"], url_path="publish-all")
    def publish_all(self, request):
        academic_year = request.data.get("academic_year")
        exam_id = request.data.get("exam_id")
        title = request.data.get("title")
        action_val = request.data.get("action", "PUBLISH")  # PUBLISH / UNPUBLISH

        qs = SeatingAllocation.objects.filter(exam__school=request.user.school)
        if academic_year: qs = qs.filter(exam__academic_year_id=academic_year)
        if exam_id: qs = qs.filter(exam_id=exam_id)
        if title and str(title).strip().upper() != "ALL":
            qs = qs.filter(Q(exam__title__iexact=str(title).strip()) | Q(exam__title__icontains=str(title).strip()))

        is_pub = action_val == "PUBLISH"
        cnt = qs.update(is_published=is_pub)
        return Response({"message": f"Updated {cnt} seating allocation record(s) to {'PUBLISHED' if is_pub else 'DRAFT'}.", "count": cnt})

    @action(detail=False, methods=["post"], url_path="auto-generate")
    def auto_generate(self, request):
        exam_id = request.data.get("exam_id")
        if not exam_id:
            return Response({"error": "exam_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        exam = Exam.objects.filter(id=exam_id, school=request.user.school).first()
        if not exam:
            return Response({"error": "Exam not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get all students for this exam's class & division
        students = Student.objects.filter(school=request.user.school, school_class=exam.class_group)
        if exam.division and str(exam.division).strip().upper() not in ["ALL", ""]:
            div_val = str(exam.division).strip()
            students = students.filter(
                Q(division__iexact=div_val) | Q(division__isnull=True) | Q(division="")
            )

        # Get available exam rooms
        rooms = list(ExamRoom.objects.filter(school=request.user.school, is_active=True).order_by("room_number"))
        if not rooms:
            return Response({"error": "No active Exam Rooms found. Please add exam rooms first."}, status=status.HTTP_400_BAD_REQUEST)

        # Strategy: ROLL_NO, NAME (first name), SURNAME (last name), GR_NO, RANDOM
        strategy = str(request.data.get("strategy", request.data.get("sort_by", "ROLL_NO"))).upper()

        students = list(students)

        if strategy == "RANDOM":
            random.shuffle(students)
        elif strategy in ["NAME", "FIRST_NAME"]:
            students.sort(key=lambda s: ((s.name or "").lower(), (s.surname or "").lower()))
        elif strategy in ["SURNAME", "LAST_NAME"]:
            students.sort(key=lambda s: ((s.surname or "").lower(), (s.name or "").lower()))
        elif strategy == "GR_NO":
            students.sort(key=lambda s: (s.gr_no or "").lower())
        else:  # ROLL_NO (default)
            def student_sort_key(s):
                r = getattr(s, "roll_no", None)
                if r and str(r).strip().isdigit():
                    return (0, int(str(r).strip()))
                return (1, (s.name or "").lower())
            students.sort(key=student_sort_key)

        created_count = 0
        with transaction.atomic():
            # Clear existing seating allocation for this exam
            SeatingAllocation.objects.filter(exam=exam).delete()

            student_idx = 0
            for room in rooms:
                seat_num = 1
                while seat_num <= room.capacity and student_idx < len(students):
                    st = students[student_idx]
                    seat_str = f"Seat {seat_num:03d}"

                    SeatingAllocation.objects.create(
                        exam=exam,
                        student=st,
                        room=room,
                        seat_number=seat_str,
                        is_published=True,
                    )
                    seat_num += 1
                    student_idx += 1

                if student_idx >= len(students):
                    break

        return Response(
            {
                "message": f"Successfully auto-generated seating allocation for {student_idx} student(s) across {len(rooms)} room(s) using {strategy} ordering.",
                "allocated_count": student_idx,
                "total_students": len(students),
                "strategy": strategy,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="bulk-auto-generate")
    def bulk_auto_generate(self, request):
        academic_year = request.data.get("academic_year")
        title = request.data.get("title")
        strategy = str(request.data.get("strategy", request.data.get("sort_by", "ROLL_NO"))).upper()
        class_id = request.data.get("class_id") or request.data.get("school_class")
        division = request.data.get("division")

        if not academic_year or not title:
            return Response({"error": "academic_year and title are required"}, status=status.HTTP_400_BAD_REQUEST)

        exams = Exam.objects.filter(school=request.user.school, academic_year_id=academic_year)
        if title and str(title).strip().upper() != "ALL":
            clean_title = str(title).strip()
            exams = exams.filter(Q(title__iexact=clean_title) | Q(title__icontains=clean_title))

        if class_id and str(class_id).strip().upper() != "ALL":
            if str(class_id).isdigit():
                exams = exams.filter(class_group_id=int(class_id))
            else:
                exams = exams.filter(class_group__school_class__iexact=str(class_id).strip())

        if division and str(division).strip().upper() != "ALL":
            div_val = str(division).strip()
            if div_val.lower().startswith("div "):
                div_val = div_val[4:].strip()
            elif div_val.lower().startswith("div"):
                div_val = div_val[3:].strip()
            exams = exams.filter(
                Q(division__iexact=div_val) | Q(division__iexact=f"Div {div_val}") | Q(division__isnull=True) | Q(division="")
            )

        if not exams.exists():
            return Response({"error": "No exams found for this configuration."}, status=status.HTTP_404_NOT_FOUND)

        rooms = list(ExamRoom.objects.filter(school=request.user.school, is_active=True).order_by("room_number"))
        if not rooms:
            return Response({"error": "No active Exam Rooms found. Please add exam rooms first."}, status=status.HTTP_400_BAD_REQUEST)

        # Group exams by timeslot (exam_date, start_time)
        timeslots = {}
        for ex in exams:
            ts = (ex.exam_date, ex.start_time)
            if ts not in timeslots:
                timeslots[ts] = []
            timeslots[ts].append(ex)

        total_allocated = 0
        with transaction.atomic():
            # Clear existing seating for all these exams
            SeatingAllocation.objects.filter(exam__in=exams).delete()

            for ts, ts_exams in timeslots.items():
                # Get all students for these exams
                ts_students_with_exam = []
                for ex in ts_exams:
                    st_qs = Student.objects.filter(school=request.user.school, school_class=ex.class_group)
                    if ex.division and str(ex.division).strip().upper() not in ["ALL", ""]:
                        div_val = str(ex.division).strip()
                        st_qs = st_qs.filter(
                            Q(division__iexact=div_val) | Q(division__isnull=True) | Q(division="")
                        )
                    for st in st_qs:
                        ts_students_with_exam.append((st, ex))

                if strategy == "RANDOM":
                    random.shuffle(ts_students_with_exam)
                elif strategy in ["NAME", "FIRST_NAME"]:
                    ts_students_with_exam.sort(key=lambda item: ((item[0].name or "").lower(), (item[0].surname or "").lower()))
                elif strategy in ["SURNAME", "LAST_NAME"]:
                    ts_students_with_exam.sort(key=lambda item: ((item[0].surname or "").lower(), (item[0].name or "").lower()))
                elif strategy == "GR_NO":
                    ts_students_with_exam.sort(key=lambda item: (item[0].gr_no or "").lower())
                else:  # ROLL_NO (default)
                    def student_sort_key(item):
                        s, _ = item
                        r = getattr(s, "roll_no", None)
                        if r and str(r).strip().isdigit():
                            return (0, int(str(r).strip()))
                        return (1, (s.name or "").lower())
                    ts_students_with_exam.sort(key=student_sort_key)

                student_idx = 0
                for room in rooms:
                    seat_num = 1
                    while seat_num <= room.capacity and student_idx < len(ts_students_with_exam):
                        st, ex = ts_students_with_exam[student_idx]
                        seat_str = f"Seat {seat_num:03d}"

                        SeatingAllocation.objects.create(
                            exam=ex,
                            student=st,
                            room=room,
                            seat_number=seat_str,
                            is_published=True,
                        )
                        seat_num += 1
                        student_idx += 1
                        total_allocated += 1

                    if student_idx >= len(ts_students_with_exam):
                        break

        return Response(
            {
                "message": f"Successfully bulk-generated seating for {total_allocated} student(s) across {len(rooms)} room(s) for all '{title}' exams using {strategy} ordering.",
                "allocated_count": total_allocated,
                "total_exams_processed": len(exams),
                "strategy": strategy,
            },
            status=status.HTTP_200_OK,
        )



class SubjectMarksEntryViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SubjectMarksEntrySerializer

    def get_queryset(self):
        qs = Result.objects.filter(exam__school=self.request.user.school)
        exam_id = self.request.query_params.get("exam")
        if exam_id:
            qs = qs.filter(exam_id=exam_id)
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-save")
    def bulk_save(self, request):
        exam_id = request.data.get("exam_id")
        marks_data = request.data.get("marks", [])  # [{student_id: 1, marks_obtained: 85, is_absent: false, remarks: "", status: "DRAFT"|"SUBMITTED"}]
        submit_status = request.data.get("status", None)

        if not exam_id or not isinstance(marks_data, list):
            return Response({"error": "exam_id and marks list are required"}, status=status.HTTP_400_BAD_REQUEST)

        exam = Exam.objects.filter(id=exam_id, school=request.user.school).first()
        if not exam:
            return Response({"error": "Exam not found"}, status=status.HTTP_404_NOT_FOUND)

        is_admin = check_is_admin_or_clerk(request.user)
        is_ct = check_is_class_teacher(request.user, exam.class_group, exam.division)

        # Check if marks for this class are already locked by Class Teacher verification
        is_verified_locked = ClassTeacherMarksVerification.objects.filter(
            school=request.user.school,
            academic_year=exam.academic_year,
            school_class=exam.class_group,
            status="VERIFIED"
        ).exists()

        if is_verified_locked and not is_admin:
            return Response(
                {"error": "Marks for this class have been verified and locked by the Class Teacher."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Check existing result status
        existing_results = Result.objects.filter(exam=exam)
        has_submitted_marks = existing_results.filter(status__in=["SUBMITTED", "VERIFIED"]).exists()

        # If user is only a Subject Teacher (neither Class Teacher nor Admin)
        if not is_admin and not is_ct:
            staff = getattr(request.user, "staff", None)
            if not staff:
                return Response({"error": "Staff profile not found."}, status=status.HTTP_403_FORBIDDEN)

            is_assigned = AssignClass.objects.filter(
                school=request.user.school,
                subject=exam.subject,
                teacher=staff
            ).exists()
            if not is_assigned:
                return Response(
                    {"error": "You are not authorized to enter marks for this subject as you are not assigned to it."},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Once submitted to Class Teacher, Subject Teacher CANNOT edit
            if has_submitted_marks:
                return Response(
                    {
                        "error": "Marks for this subject have already been submitted to the Class Teacher. "
                                 "Subject teachers cannot edit submitted marks. Only the Class Teacher or Administrator has update authority."
                    },
                    status=status.HTTP_403_FORBIDDEN
                )

        saved_count = 0
        target_status = submit_status or "DRAFT"

        with transaction.atomic():
            for item in marks_data:
                st_id = item.get("student_id")
                obtained = item.get("marks_obtained")
                is_absent = item.get("is_absent", False)
                remarks = item.get("remarks", "")
                row_status = submit_status or item.get("status") or target_status

                if row_status not in ["DRAFT", "SUBMITTED", "VERIFIED", "SENT_BACK"]:
                    row_status = "DRAFT"

                if st_id is not None:
                    # Calculate grade
                    grade_str = ""
                    if not is_absent and obtained is not None:
                        pct = (float(obtained) / float(exam.max_marks or 100)) * 100
                        if pct >= 90: grade_str = "A+"
                        elif pct >= 80: grade_str = "A"
                        elif pct >= 70: grade_str = "B+"
                        elif pct >= 60: grade_str = "B"
                        elif pct >= 50: grade_str = "C"
                        elif pct >= 33: grade_str = "D"
                        else: grade_str = "F"

                    staff = getattr(request.user, "staff", None)
                    Result.objects.update_or_create(
                        exam=exam,
                        student_id=st_id,
                        defaults={
                            "entered_by": staff,
                            "marks_obtained": Decimal(str(obtained)) if (obtained is not None and not is_absent) else None,
                            "max_marks": exam.max_marks,
                            "is_absent": is_absent,
                            "grade": grade_str,
                            "remarks": remarks,
                            "status": row_status,
                        },
                    )
                    saved_count += 1

        action_word = "submitted to Class Teacher" if target_status == "SUBMITTED" else "saved as draft"
        return Response({
            "message": f"Successfully {action_word} marks for {saved_count} student(s).",
            "count": saved_count,
            "status": target_status
        })


class TeacherAssessmentViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TeacherAssessmentScoreSerializer

    def get_queryset(self):
        qs = TeacherAssessmentScore.objects.filter(school=self.request.user.school)
        year_id = self.request.query_params.get("academic_year")
        st_id = self.request.query_params.get("student")
        subj_id = self.request.query_params.get("subject")
        if year_id: qs = qs.filter(academic_year_id=year_id)
        if st_id: qs = qs.filter(student_id=st_id)
        if subj_id: qs = qs.filter(subject_id=subj_id)
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-save")
    def bulk_save(self, request):
        year_id = request.data.get("academic_year")
        subj_id = request.data.get("subject_id")
        class_id = request.data.get("school_class")
        scores = request.data.get("scores", [])  # [{student_id: 1, score: 8.5, max_score: 10}]
        staff = getattr(request.user, "staff", None)

        if (not class_id or str(class_id).strip() == "") and isinstance(scores, list) and len(scores) > 0:
            first_st_id = scores[0].get("student_id")
            if first_st_id:
                st = Student.objects.filter(id=first_st_id, school=request.user.school).first()
                if st and st.school_class_id:
                    class_id = st.school_class_id

        if not year_id or not subj_id or not class_id or not isinstance(scores, list):
            return Response({"error": "academic_year, subject_id, school_class, and scores list are required"}, status=status.HTTP_400_BAD_REQUEST)

        # Check verification lock
        is_locked = ClassTeacherMarksVerification.objects.filter(
            school=request.user.school,
            academic_year_id=year_id,
            school_class_id=class_id,
            status="VERIFIED"
        ).exists()

        is_admin = check_is_admin_or_clerk(request.user)
        if is_locked and not is_admin:
            return Response({"error": "Marks for this class have been verified and locked by the Class Teacher."}, status=status.HTTP_400_BAD_REQUEST)

        is_ct = check_is_class_teacher(request.user, class_id)

        saved = 0
        with transaction.atomic():
            for item in scores:
                st_id = item.get("student_id")
                sc_val = item.get("score")
                max_sc = item.get("max_score", 10.0)

                if st_id and sc_val is not None and staff:
                    TeacherAssessmentScore.objects.update_or_create(
                        school=request.user.school,
                        academic_year_id=year_id,
                        student_id=st_id,
                        subject_id=subj_id,
                        defaults={
                            "teacher": staff,
                            "is_class_teacher": is_ct,
                            "score": Decimal(str(sc_val)),
                            "max_score": Decimal(str(max_sc)),
                            "remarks": item.get("remarks", ""),
                        },
                    )
                    saved += 1

        return Response({"message": f"Saved teacher assessments for {saved} student(s).", "count": saved})


class ClassTeacherVerificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ClassTeacherMarksVerificationSerializer

    def get_queryset(self):
        qs = ClassTeacherMarksVerification.objects.filter(school=self.request.user.school)
        year_id = self.request.query_params.get("academic_year")
        term_id = self.request.query_params.get("exam_term")
        class_id = self.request.query_params.get("school_class")
        class_name = self.request.query_params.get("class_name")
        div = self.request.query_params.get("division")

        if not class_id and class_name:
            sc = SchoolClass.objects.filter(school=self.request.user.school, school_class=class_name).first()
            if sc:
                class_id = sc.id

        if year_id: qs = qs.filter(academic_year_id=year_id)
        if term_id: qs = qs.filter(exam_term_id=term_id)
        if class_id: qs = qs.filter(school_class_id=class_id)
        if div: qs = qs.filter(division=div)
        return qs

    def create(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not data.get("school_class") and data.get("class_name"):
            sc = SchoolClass.objects.filter(school=request.user.school, school_class=data.get("class_name")).first()
            if sc:
                data["school_class"] = sc.id
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not data.get("school_class") and data.get("class_name"):
            sc = SchoolClass.objects.filter(school=request.user.school, school_class=data.get("class_name")).first()
            if sc:
                data["school_class"] = sc.id

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def perform_create(self, serializer):
        teacher = getattr(self.request.user, "staff", None)
        from rest_framework import serializers
        if not teacher:
            raise serializers.ValidationError("Only staff members can verify marks.")

        status_val = serializer.validated_data.get("status", "VERIFIED")
        
        class_name = self.request.data.get("class_name")
        if not serializer.validated_data.get("school_class") and class_name:
            sc = SchoolClass.objects.filter(school=self.request.user.school, school_class=class_name).first()
            if sc:
                serializer.validated_data["school_class"] = sc

        school_class_obj = serializer.validated_data.get("school_class")
        year_obj = serializer.validated_data.get("academic_year")

        if status_val == "VERIFIED":
            serializer.save(school=self.request.user.school, class_teacher=teacher, verified_at=timezone.now())
            if school_class_obj and year_obj:
                Result.objects.filter(
                    exam__school=self.request.user.school,
                    exam__academic_year=year_obj,
                    exam__class_group=school_class_obj
                ).update(status="VERIFIED")
        elif status_val == "SENT_BACK":
            serializer.save(school=self.request.user.school, class_teacher=teacher, verified_at=None)
            if school_class_obj and year_obj:
                Result.objects.filter(
                    exam__school=self.request.user.school,
                    exam__academic_year=year_obj,
                    exam__class_group=school_class_obj
                ).update(status="SENT_BACK")
        else:
            serializer.save(school=self.request.user.school, class_teacher=teacher, verified_at=None)

    def perform_update(self, serializer):
        status_val = serializer.validated_data.get("status", "VERIFIED")
        
        class_name = self.request.data.get("class_name")
        if not serializer.validated_data.get("school_class") and class_name:
            sc = SchoolClass.objects.filter(school=self.request.user.school, school_class=class_name).first()
            if sc:
                serializer.validated_data["school_class"] = sc

        school_class_obj = serializer.validated_data.get("school_class") or serializer.instance.school_class
        year_obj = serializer.validated_data.get("academic_year") or serializer.instance.academic_year

        if status_val == "VERIFIED":
            serializer.save(verified_at=timezone.now())
            if school_class_obj and year_obj:
                Result.objects.filter(
                    exam__school=self.request.user.school,
                    exam__academic_year=year_obj,
                    exam__class_group=school_class_obj
                ).update(status="VERIFIED")
        elif status_val == "SENT_BACK":
            serializer.save(verified_at=None)
            if school_class_obj and year_obj:
                Result.objects.filter(
                    exam__school=self.request.user.school,
                    exam__academic_year=year_obj,
                    exam__class_group=school_class_obj
                ).update(status="SENT_BACK")
        else:
            serializer.save(verified_at=None)

    @action(detail=False, methods=["post"], url_path="bulk-save-marks")
    def bulk_save_marks(self, request):
        """Allows Class Teacher to directly edit, update, and save any student marks across all exams/assessments."""
        year_id = request.data.get("academic_year")
        class_id = request.data.get("school_class")
        class_name = request.data.get("class_name")
        div = request.data.get("division")
        marks_entries = request.data.get("marks", [])  # [{ exam_id, student_id, marks_obtained, is_absent, remarks }]
        ta_entries = request.data.get("teacher_assessments", [])  # [{ student_id, subject_id, score, max_score, remarks }]

        if not class_id and class_name:
            sc = SchoolClass.objects.filter(school=request.user.school, school_class=class_name).first()
            if sc:
                class_id = sc.id

        if not year_id or not class_id:
            return Response({"error": "academic_year and school_class are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Check permission: Must be Class Teacher or Admin
        is_admin = check_is_admin_or_clerk(request.user)
        is_ct = check_is_class_teacher(request.user, class_id, div)

        if not is_admin and not is_ct:
            return Response(
                {"error": "Only the assigned Class Teacher or an Administrator has authority to edit all class marks."},
                status=status.HTTP_403_FORBIDDEN
            )

        staff = getattr(request.user, "staff", None)
        saved_marks_count = 0
        saved_ta_count = 0

        with transaction.atomic():
            for m in marks_entries:
                ex_id = m.get("exam_id")
                st_id = m.get("student_id")
                if not ex_id or not st_id:
                    continue
                exam = Exam.objects.filter(id=ex_id, school=request.user.school).first()
                if not exam:
                    continue

                obtained = m.get("marks_obtained")
                is_absent = m.get("is_absent", False)
                remarks = m.get("remarks", "")

                grade_str = ""
                if not is_absent and obtained is not None:
                    pct = (float(obtained) / float(exam.max_marks or 100)) * 100
                    if pct >= 90: grade_str = "A+"
                    elif pct >= 80: grade_str = "A"
                    elif pct >= 70: grade_str = "B+"
                    elif pct >= 60: grade_str = "B"
                    elif pct >= 50: grade_str = "C"
                    elif pct >= 33: grade_str = "D"
                    else: grade_str = "F"

                Result.objects.update_or_create(
                    exam=exam,
                    student_id=st_id,
                    defaults={
                        "entered_by": staff,
                        "marks_obtained": Decimal(str(obtained)) if (obtained is not None and not is_absent) else None,
                        "max_marks": exam.max_marks,
                        "is_absent": is_absent,
                        "grade": grade_str,
                        "remarks": remarks,
                        "status": "SUBMITTED",
                    },
                )
                saved_marks_count += 1

            for ta in ta_entries:
                st_id = ta.get("student_id")
                subj_id = ta.get("subject_id")
                sc_val = ta.get("score")
                max_sc = ta.get("max_score", 10.0)
                if st_id and subj_id and sc_val is not None:
                    TeacherAssessmentScore.objects.update_or_create(
                        school=request.user.school,
                        academic_year_id=year_id,
                        student_id=st_id,
                        subject_id=subj_id,
                        defaults={
                            "teacher": staff,
                            "is_class_teacher": True,
                            "score": Decimal(str(sc_val)),
                            "max_score": Decimal(str(max_sc)),
                            "remarks": ta.get("remarks", ""),
                        },
                    )
                    saved_ta_count += 1

        return Response({
            "message": f"Successfully saved {saved_marks_count} exam mark(s) and {saved_ta_count} teacher assessment(s).",
            "saved_marks": saved_marks_count,
            "saved_assessments": saved_ta_count
        })

    @action(detail=False, methods=["get"], url_path="marks-grid")
    def marks_grid(self, request):
        year_id = request.query_params.get("academic_year")
        term_id = request.query_params.get("exam_term")
        class_id = request.query_params.get("school_class")
        class_name = request.query_params.get("class_name")
        div = request.query_params.get("division")

        if not class_id and class_name:
            sc = SchoolClass.objects.filter(school=request.user.school, school_class=class_name).first()
            if sc:
                class_id = sc.id

        if not year_id or not class_id:
            return Response({"error": "academic_year and school_class (or valid class_name) are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        students_qs = Student.objects.filter(school=request.user.school, school_class_id=class_id, is_active=True)
        exams_qs = Exam.objects.filter(
            school=request.user.school, 
            academic_year_id=year_id, 
            class_group_id=class_id
        ).select_related("subject", "exam_term").order_by("exam_term_id", "title", "subject__name")

        if term_id and str(term_id).strip().upper() not in ["ALL", ""]:
            t_str = str(term_id).strip()
            if t_str.isdigit():
                exams_qs = exams_qs.filter(Q(exam_term_id=int(t_str)) | Q(title__iexact=t_str))
            else:
                exams_qs = exams_qs.filter(Q(title__iexact=t_str) | Q(exam_term__name__iexact=t_str))

        if div and str(div).strip().upper() not in ["ALL", ""]:
            div_val = str(div).strip()
            if div_val.lower().startswith("div "):
                div_val = div_val[4:].strip()
            elif div_val.lower().startswith("div"):
                div_val = div_val[3:].strip()
            students_qs = students_qs.filter(
                Q(division__iexact=div_val) |
                Q(division__iexact=f"Div {div_val}") |
                Q(division__iexact=f"Div ({div_val})") |
                Q(division__isnull=True) |
                Q(division="")
            )
            exams_qs = exams_qs.filter(
                Q(division__iexact=div_val) |
                Q(division__iexact=f"Div {div_val}") |
                Q(division__isnull=True) |
                Q(division="")
            )

        results = list(Result.objects.filter(exam__in=exams_qs, student__in=students_qs).select_related("exam__subject"))

        teacher_assessments = list(
            TeacherAssessmentScore.objects.filter(
                school=request.user.school,
                academic_year_id=year_id,
                student__in=students_qs
            ).select_related("subject")
        )

        # 1. Group Exams by Term / Title
        terms_map = {}
        for ex in exams_qs:
            term_key = ex.exam_term.name if ex.exam_term else (ex.title.strip() if ex.title else "General Exam")
            term_id_val = str(ex.exam_term_id) if ex.exam_term_id else term_key
            if term_id_val not in terms_map:
                terms_map[term_id_val] = {
                    "id": term_id_val,
                    "name": term_key,
                    "subjects_map": {}
                }
            if ex.subject_id and ex.subject_id not in terms_map[term_id_val]["subjects_map"]:
                terms_map[term_id_val]["subjects_map"][ex.subject_id] = {
                    "id": ex.subject_id,
                    "exam_id": ex.id,
                    "name": ex.subject.name,
                    "max_marks": float(ex.max_marks)
                }

        terms_list = []
        for t_info in terms_map.values():
            terms_list.append({
                "id": t_info["id"],
                "name": t_info["name"],
                "subjects": list(t_info["subjects_map"].values())
            })

        # 2. Teacher Assessment Subjects
        ta_subjects_map = {}
        for ta in teacher_assessments:
            if ta.subject_id and ta.subject_id not in ta_subjects_map:
                ta_subjects_map[ta.subject_id] = {
                    "id": ta.subject_id,
                    "name": ta.subject.name,
                    "max_score": float(ta.max_score)
                }

        # 3. Flat distinct subjects across all evaluations
        all_subjects_map = {}
        for ex in exams_qs:
            if ex.subject_id and ex.subject_id not in all_subjects_map:
                all_subjects_map[ex.subject_id] = {"id": ex.subject_id, "name": ex.subject.name}
        for ta in teacher_assessments:
            if ta.subject_id and ta.subject_id not in all_subjects_map:
                all_subjects_map[ta.subject_id] = {"id": ta.subject_id, "name": ta.subject.name}

        # Check Class Teacher verification records
        ct_verif_qs = ClassTeacherMarksVerification.objects.filter(
            school=request.user.school,
            academic_year_id=year_id,
            school_class_id=class_id,
        )
        if term_id:
            ct_verif_qs = ct_verif_qs.filter(Q(exam_term_id=term_id) | Q(exam_term__isnull=True))
        if div and str(div).strip().upper() not in ["ALL", ""]:
            div_val = str(div).strip()
            if div_val.lower().startswith("div "):
                div_val = div_val[4:].strip()
            elif div_val.lower().startswith("div"):
                div_val = div_val[3:].strip()
            ct_verif_qs = ct_verif_qs.filter(Q(division__iexact=div_val) | Q(division__isnull=True) | Q(division=""))

        ct_verif_map = {}
        for cv in ct_verif_qs:
            t_id = str(cv.exam_term_id) if cv.exam_term_id else "ALL"
            ct_verif_map[t_id] = cv

        is_ct_user = check_is_class_teacher(request.user, class_id, div)
        is_principal_view = not is_ct_user

        def check_is_submitted(ex, r):
            term_key = str(ex.exam_term_id) if ex.exam_term_id else "ALL"
            cv = ct_verif_map.get(term_key) or ct_verif_map.get("ALL")
            if cv and cv.status == "VERIFIED":
                return True
            if r and r.status == "VERIFIED":
                return True
            return False

        # 4. Construct per-student records
        students_list = []
        has_any_submitted_marks = False

        for st in students_qs:
            st_full_name = " ".join([p for p in [st.surname, st.name, st.father_name] if p and str(p).strip()]) or f"Student #{st.id}"
            st_data = {
                "id": st.id,
                "name": st_full_name,
                "roll_no": st.roll_no or "",
                "gr_no": st.gr_no or "",
                "terms_marks": {},
                "teacher_assessments": {},
                "marks": {}
            }

            st_results = [r for r in results if r.student_id == st.id]
            for r in st_results:
                ex = r.exam
                is_sub = check_is_submitted(ex, r)
                if is_sub:
                    has_any_submitted_marks = True

                # If Principal is viewing and marks are NOT submitted by Class Teacher yet, do not expose draft marks
                if is_principal_view and not is_sub:
                    score_val = None
                    status_val = "PENDING_CLASS_TEACHER_SUBMISSION"
                else:
                    score_val = float(r.marks_obtained) if r.marks_obtained is not None else None
                    status_val = r.status

                term_key = ex.exam_term.name if ex.exam_term else (ex.title.strip() if ex.title else "General Exam")
                term_id_val = str(ex.exam_term_id) if ex.exam_term_id else term_key
                if term_id_val not in st_data["terms_marks"]:
                    st_data["terms_marks"][term_id_val] = {}

                subj_id = str(ex.subject_id)
                st_data["terms_marks"][term_id_val][subj_id] = {
                    "exam_id": ex.id,
                    "score": score_val,
                    "max": float(r.max_marks),
                    "is_absent": r.is_absent if (not is_principal_view or is_sub) else False,
                    "status": status_val,
                    "remarks": r.remarks or "",
                    "is_submitted_to_principal": is_sub,
                }
                st_data["marks"][subj_id] = {
                    "exam_id": ex.id,
                    "score": score_val,
                    "max": float(r.max_marks),
                    "is_absent": r.is_absent if (not is_principal_view or is_sub) else False,
                    "status": status_val,
                    "remarks": r.remarks or "",
                    "is_submitted_to_principal": is_sub,
                }

            st_tas = [ta for ta in teacher_assessments if ta.student_id == st.id]
            for ta in st_tas:
                subj_id = str(ta.subject_id)
                st_data["teacher_assessments"][subj_id] = {
                    "score": float(ta.score) if ta.score is not None else None,
                    "max_score": float(ta.max_score),
                    "remarks": ta.remarks or ""
                }

            students_list.append(st_data)

        def student_sort_key(s):
            r = str(s.get("roll_no") or "").strip()
            if r.isdigit():
                return (0, int(r), s.get("name", ""))
            return (1, 999999, s.get("name", ""))
        students_list.sort(key=student_sort_key)

        first_verif = ct_verif_qs.first()
        is_all_submitted = ct_verif_qs.filter(status="VERIFIED").exists()

        return Response({
            "terms": terms_list,
            "teacher_assessment_subjects": list(ta_subjects_map.values()),
            "subjects": list(all_subjects_map.values()),
            "students": students_list,
            "is_submitted_to_principal": is_all_submitted,
            "has_submitted_marks": has_any_submitted_marks,
            "class_teacher_verification_status": first_verif.status if first_verif else "PENDING",
            "class_teacher_name": first_verif.class_teacher.name if first_verif and first_verif.class_teacher else None,
            "verified_at": first_verif.verified_at if first_verif else None,
        })






class ResultProcessingViewSet(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.data.get("academic_year")
        class_id = request.data.get("school_class")
        div = request.data.get("division")

        if not year_id or not class_id:
            return Response({"error": "academic_year and school_class are required"}, status=status.HTTP_400_BAD_REQUEST)

        academic_year = AcademicYear.objects.filter(id=year_id, school=school).first()
        school_class = SchoolClass.objects.filter(id=class_id, school=school).first()

        if not academic_year or not school_class:
            return Response({"error": "Academic Year or School Class not found"}, status=status.HTTP_404_NOT_FOUND)

        res = ResultCalculationEngine.calculate_class_results(
            school=school,
            academic_year=academic_year,
            school_class=school_class,
            division=div
        )

        return Response(res, status=status.HTTP_200_OK)


class ResultPublishView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.query_params.get("academic_year")
        class_id = request.query_params.get("school_class")
        div = request.query_params.get("division")

        qs = FinalStudentResult.objects.filter(school=school, academic_year_id=year_id, school_class_id=class_id)
        if div and div != "ALL":
            qs = qs.filter(division=div)

        serializer = FinalStudentResultSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.data.get("academic_year")
        class_id = request.data.get("school_class")
        div = request.data.get("division")
        publish_action = request.data.get("action", "PUBLISH")  # PUBLISH or UNPUBLISH

        qs = FinalStudentResult.objects.filter(school=school, academic_year_id=year_id, school_class_id=class_id)
        if div and div != "ALL":
            qs = qs.filter(division=div)

        now = timezone.now()
        student_ids = list(qs.values_list("student_id", flat=True))
        if not student_ids and class_id:
            student_ids = list(Student.objects.filter(school=school, school_class_id=class_id).values_list("id", flat=True))

        if publish_action == "PUBLISH":
            cnt = qs.update(status="PUBLISHED", is_published=True, published_at=now)
            if student_ids:
                Result.objects.filter(student_id__in=student_ids).update(is_published=True)
            msg = f"Successfully published final results for {cnt} student(s)."
        else:
            cnt = qs.update(status="APPROVED", is_published=False, published_at=None)
            if student_ids:
                Result.objects.filter(student_id__in=student_ids).update(is_published=False)
            msg = f"Unpublished final results for {cnt} student(s)."

        return Response({"message": msg, "count": cnt})


class ResultDashboardSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.query_params.get("academic_year")

        if not year_id:
            active_year = AcademicYear.objects.filter(school=school, is_active=True).first()
            if not active_year:
                active_year = AcademicYear.objects.filter(school=school).first()
            if not active_year:
                return Response({
                    "academic_year_id": None,
                    "academic_year_name": "No Academic Year Found",
                    "weightage": {"is_configured": False, "status": "DRAFT", "total_weightage": 0, "is_active": False, "components": []},
                    "terms": [],
                    "attendance": {"is_available": False, "total_logs": 0, "status": "No Year"},
                    "teacher_assessment": {"total_students": 0, "assessed_students": 0, "percentage": 0, "status": "No Year"},
                    "overall_readiness": {"is_ready": False, "status": "NOT_READY", "blockers": ["No Academic Year found"], "warnings": []},
                    "counts": {"total_exams": 0, "scheduled_exams": 0, "completed_exams": 0, "ready_count": 0, "approved_count": 0, "published_count": 0, "total_students": 0}
                })
            academic_year = active_year
        else:
            academic_year = AcademicYear.objects.filter(id=year_id, school=school).first()
            if not academic_year:
                return Response({"error": "Academic Year not found"}, status=status.HTTP_404_NOT_FOUND)

        summary = ResultCalculationEngine.get_dashboard_summary(school, academic_year)
        return Response(summary)


class ResultReadinessCheckAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.query_params.get("academic_year")
        class_id = request.query_params.get("school_class")
        div = request.query_params.get("division")

        if not year_id:
            return Response({"error": "academic_year is required"}, status=status.HTTP_400_BAD_REQUEST)

        academic_year = AcademicYear.objects.filter(id=year_id, school=school).first()
        if not academic_year:
            return Response({"error": "Academic Year not found"}, status=status.HTTP_404_NOT_FOUND)

        school_class = None
        if class_id:
            school_class = SchoolClass.objects.filter(id=class_id, school=school).first()

        readiness = ResultCalculationEngine.check_readiness(
            school=school,
            academic_year=academic_year,
            school_class=school_class,
            division=div
        )

        return Response(readiness)


class MarksOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        school = request.user.school
        year_id = request.query_params.get("academic_year")
        class_id = request.query_params.get("school_class")
        term_id = request.query_params.get("exam_term")

        qs = Exam.objects.filter(school=school).select_related(
            "subject", "class_group", "exam_term"
        ).order_by("class_group_id", "exam_term_id", "subject__name")

        if year_id: qs = qs.filter(academic_year_id=year_id)
        if class_id: qs = qs.filter(class_group_id=class_id)
        if term_id: qs = qs.filter(exam_term_id=term_id)

        rows = []
        for ex in qs:
            cls = ex.class_group
            div = ex.division or "ALL"
            students_qs = Student.objects.filter(school=school, school_class=cls, is_active=True)
            if div != "ALL":
                students_qs = students_qs.filter(division=div)
            
            total_students = students_qs.count()
            results = Result.objects.filter(exam=ex, student__in=students_qs)
            entered_count = results.count()
            submitted_count = results.filter(status__in=["SUBMITTED", "VERIFIED"]).count()
            absent_count = results.filter(is_absent=True).count()

            # Check verification
            verif = ClassTeacherMarksVerification.objects.filter(
                school=school,
                academic_year=ex.academic_year,
                school_class=cls,
                exam_term=ex.exam_term,
            )
            if div != "ALL":
                verif = verif.filter(division=div)
            verif_rec = verif.first()
            is_verified = verif_rec.status == "VERIFIED" if verif_rec else False
            verif_status = verif_rec.status if verif_rec else "PENDING"

            completion_pct = round((entered_count / total_students * 100), 1) if total_students > 0 else 0.0

            rows.append({
                "exam_id": ex.id,
                "term_name": ex.exam_term.name if ex.exam_term else ex.title,
                "class_id": cls.id if cls else None,
                "class_name": cls.school_class if cls else "N/A",
                "division": div,
                "subject_id": ex.subject_id,
                "subject_name": ex.subject.name if ex.subject else "N/A",
                "max_marks": float(ex.max_marks),
                "passing_marks": float(ex.passing_marks),
                "total_students": total_students,
                "entered_count": entered_count,
                "submitted_count": submitted_count,
                "absent_count": absent_count,
                "completion_percentage": completion_pct,
                "verification_status": verif_status,
                "is_verified": is_verified,
                "exam_date": str(ex.exam_date),
                "time": f"{str(ex.start_time)[:5]} - {str(ex.end_time)[:5]}",
                "status": ex.status,
            })

        return Response({"exams": rows, "total_count": len(rows)})


class StudentExamScheduleView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        school = user.school
        student = getattr(user, "student_profile", None) or Student.objects.filter(school=school, email=user.email).first()

        if not student:
            # Check if parent
            student_id = request.query_params.get("student_id")
            if student_id:
                student = Student.objects.filter(id=student_id, school=school).first()

        if not student:
            return Response({"error": "Student profile not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get published exams for student's class and division
        exams_qs = Exam.objects.filter(
            school=school,
            class_group=student.school_class,
            status="PUBLISHED"
        ).filter(
            Q(division__isnull=True) | Q(division="") | Q(division="ALL") | Q(division=student.division)
        ).select_related("subject", "room", "exam_term").order_by("exam_date", "start_time")

        results = []
        for ex in exams_qs:
            # Find seating
            seating = SeatingAllocation.objects.filter(exam=ex, student=student, is_published=True).first()
            room_str = seating.room.room_number if (seating and seating.room) else (ex.room.room_number if ex.room else "TBA")
            seat_str = seating.seat_number if seating else "Not Assigned"

            results.append({
                "exam_id": ex.id,
                "term_name": ex.exam_term.name if ex.exam_term else ex.title,
                "subject_name": ex.subject.name if ex.subject else "",
                "exam_date": str(ex.exam_date),
                "day": ex.exam_date.strftime("%A") if ex.exam_date else "",
                "time": f"{str(ex.start_time)[:5]} - {str(ex.end_time)[:5]}",
                "duration_minutes": ex.duration_minutes,
                "room": room_str,
                "seat_number": seat_str,
                "max_marks": float(ex.max_marks),
                "passing_marks": float(ex.passing_marks),
                "instructions": ex.description or "",
            })

        return Response({
            "student_name": f"{student.surname or ''} {student.name or ''}".strip(),
            "roll_no": student.roll_no or "",
            "gr_no": student.gr_no or "",
            "class_name": student.school_class.school_class if student.school_class else "",
            "division": student.division or "",
            "schedule": results
        })


class StudentPublishedReportCardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        school = user.school
        student = getattr(user, "student_profile", None) or Student.objects.filter(school=school, email=user.email).first()

        student_id = request.query_params.get("student_id")
        if student_id:
            student = Student.objects.filter(id=student_id, school=school).first()

        if not student:
            return Response({"error": "Student profile not found"}, status=status.HTTP_404_NOT_FOUND)

        year_id = request.query_params.get("academic_year")
        qs = FinalStudentResult.objects.filter(
            school=school, student=student, is_published=True
        ).select_related("academic_year", "school_class")

        if year_id:
            qs = qs.filter(academic_year_id=year_id)

        final_res = qs.order_by("-academic_year_id").first()
        if not final_res:
            return Response({
                "is_published": False,
                "message": "Final result has not been published yet for this student.",
                "student_name": f"{student.surname or ''} {student.name or ''}".strip(),
                "class_name": student.school_class.school_class if student.school_class else "",
                "division": student.division or "",
            })

        # Fetch subject-wise exam marks for this student in this academic year
        exam_results = Result.objects.filter(
            student=student,
            exam__academic_year=final_res.academic_year,
            is_published=True
        ).select_related("exam__subject", "exam__exam_term")

        subject_marks = []
        for r in exam_results:
            subject_marks.append({
                "term_name": r.exam.exam_term.name if (r.exam and r.exam.exam_term) else (r.exam.title if r.exam else ""),
                "subject_name": r.exam.subject.name if (r.exam and r.exam.subject) else "",
                "marks_obtained": float(r.marks_obtained) if r.marks_obtained is not None else None,
                "max_marks": float(r.max_marks or 100),
                "is_absent": r.is_absent,
                "grade": r.grade,
                "remarks": r.remarks or "",
            })

        # Fetch teacher assessment
        ta_scores = TeacherAssessmentScore.objects.filter(
            student=student,
            academic_year=final_res.academic_year
        ).select_related("subject", "teacher")
        ta_list = []
        for ta in ta_scores:
            ta_list.append({
                "subject_name": ta.subject.name if ta.subject else "General Evaluation",
                "score": float(ta.score),
                "max_score": float(ta.max_score),
                "teacher_name": ta.teacher.name if ta.teacher else "",
                "is_class_teacher": ta.is_class_teacher,
            })

        # Fetch attendance percentage
        att_qs = StudentAttendance.objects.filter(student=student, school=school)
        total_att_days = att_qs.count()
        present_att_days = att_qs.filter(is_present=True).count()
        att_pct = round((present_att_days / total_att_days * 100), 1) if total_att_days > 0 else 100.0

        return Response({
            "is_published": True,
            "student_id": student.id,
            "student_name": f"{student.surname or ''} {student.name or ''} {student.father_name or ''}".strip(),
            "roll_no": student.roll_no or "",
            "gr_no": student.gr_no or "",
            "class_name": final_res.school_class.school_class if final_res.school_class else "",
            "division": final_res.division or "",
            "academic_year_name": final_res.academic_year.name if final_res.academic_year else "",
            "total_percentage": float(final_res.total_percentage),
            "grade": final_res.grade,
            "status": final_res.status,
            "published_at": final_res.published_at,
            "component_breakdown": final_res.component_breakdown,
            "subject_marks": subject_marks,
            "teacher_assessments": ta_list,
            "attendance": {
                "total_working_days": total_att_days,
                "present_days": present_att_days,
                "percentage": att_pct
            }
        })

