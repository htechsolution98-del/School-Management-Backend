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


class ResultWeightageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ResultWeightageConfigSerializer

    def get_queryset(self):
        school = self.request.user.school
        qs = ResultWeightageConfig.objects.filter(school=school)
        year_id = self.request.query_params.get("academic_year")
        if year_id:
            qs = qs.filter(academic_year_id=year_id)
        return qs

    def create(self, request, *args, **kwargs):
        school = request.user.school
        academic_year_id = request.data.get("academic_year")
        title = request.data.get("title", "Academic Year Dynamic Weightage")

        if not academic_year_id:
            return Response({"error": "academic_year is required"}, status=status.HTTP_400_BAD_REQUEST)

        config, created = ResultWeightageConfig.objects.get_or_create(
            school=school,
            academic_year_id=academic_year_id,
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
        
        user_groups = list(self.request.user.groups.values_list('name', flat=True)) if self.request.user else []
        is_admin_or_clerk = any(role in user_groups for role in ["PRINCIPAL", "CLERK", "admin(trustee)"])
        
        if not is_admin_or_clerk:
            staff = getattr(self.request.user, "staff", None)
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


class SeatingAllocationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = SeatingAllocationSerializer

    def get_queryset(self):
        qs = SeatingAllocation.objects.filter(exam__school=self.request.user.school).select_related("exam", "exam__subject", "exam__class_group")
        
        exam_id = self.request.query_params.get("exam")
        if exam_id:
            qs = qs.filter(exam_id=exam_id)
            
        academic_year = self.request.query_params.get("academic_year")
        title = self.request.query_params.get("title")
        if academic_year and title:
            qs = qs.filter(exam__academic_year_id=academic_year, exam__title=title)
            
        return qs

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
        if exam.division:
            students = students.filter(division=exam.division)

        # Get available exam rooms
        rooms = list(ExamRoom.objects.filter(school=request.user.school, is_active=True).order_by("room_number"))
        if not rooms:
            return Response({"error": "No active Exam Rooms found. Please add exam rooms first."}, status=status.HTTP_400_BAD_REQUEST)

        # Auto-allocate seats in available rooms
        students = list(students)

        # Sort students by roll_no or gr_no
        def student_sort_key(s):
            r = getattr(s, "roll_no", None)
            if r and str(r).strip().isdigit():
                return (0, int(str(r).strip()))
            return (1, s.gr_no or "")

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
                "message": f"Successfully auto-generated seating allocation for {student_idx} student(s) across {len(rooms)} room(s).",
                "allocated_count": student_idx,
                "total_students": len(students),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="bulk-auto-generate")
    def bulk_auto_generate(self, request):
        academic_year = request.data.get("academic_year")
        title = request.data.get("title")

        if not academic_year or not title:
            return Response({"error": "academic_year and title are required"}, status=status.HTTP_400_BAD_REQUEST)

        exams = Exam.objects.filter(school=request.user.school, academic_year_id=academic_year, title=title)
        if not exams.exists():
            return Response({"error": "No exams found for this component"}, status=status.HTTP_404_NOT_FOUND)

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
                    if ex.division:
                        st_qs = st_qs.filter(division=ex.division)
                    for st in st_qs:
                        ts_students_with_exam.append((st, ex))

                def student_sort_key(item):
                    s, _ = item
                    r = getattr(s, "roll_no", None)
                    if r and str(r).strip().isdigit():
                        return (0, int(str(r).strip()))
                    return (1, s.gr_no or "")

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
                "message": f"Successfully bulk-generated seating for {total_allocated} students across {len(rooms)} rooms for all '{title}' exams.",
                "allocated_count": total_allocated,
                "total_exams_processed": len(exams),
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
        marks_data = request.data.get("marks", [])  # [{student_id: 1, marks_obtained: 85, is_absent: false}]

        if not exam_id or not isinstance(marks_data, list):
            return Response({"error": "exam_id and marks list are required"}, status=status.HTTP_400_BAD_REQUEST)

        exam = Exam.objects.filter(id=exam_id, school=request.user.school).first()
        if not exam:
            return Response({"error": "Exam not found"}, status=status.HTTP_404_NOT_FOUND)

        staff = getattr(request.user, "staff", None)

        if staff:
            user_groups = list(request.user.groups.values_list('name', flat=True)) if request.user else []
            is_admin_or_clerk = any(role in user_groups for role in ["PRINCIPAL", "CLERK", "admin(trustee)"])
            
            if not is_admin_or_clerk:
                from .models import AssignClass
                is_assigned = AssignClass.objects.filter(subject=exam.subject, teacher=staff).exists()
                if not is_assigned:
                    return Response(
                        {"error": "You are not authorized to enter marks for this subject as you are not assigned to it."}, 
                        status=status.HTTP_403_FORBIDDEN
                    )

        saved_count = 0

        with transaction.atomic():
            for item in marks_data:
                st_id = item.get("student_id")
                obtained = item.get("marks_obtained")
                is_absent = item.get("is_absent", False)
                remarks = item.get("remarks", "")
                status_val = item.get("status", "SUBMITTED")

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
                            "status": status_val,
                        },
                    )
                    saved_count += 1

        return Response({"message": f"Successfully saved marks for {saved_count} student(s).", "count": saved_count})


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
        from .models import ClassTeacherMarksVerification
        # Teacher Assessments are usually independent of ExamTerm, but if they are verified per term, we need the term.
        # Actually, ClassTeacherMarksVerification checks for (school_class, academic_year). 
        # If any term is verified, or if the overall is verified?
        # Let's lock if ANY verification for this class/year is VERIFIED (or overall).
        is_locked = ClassTeacherMarksVerification.objects.filter(
            school=request.user.school,
            academic_year_id=year_id,
            school_class_id=class_id,
            status="VERIFIED"
        ).exists()
        
        if is_locked:
            return Response({"error": "Marks for this class have been verified and locked by the Class Teacher."}, status=status.HTTP_400_BAD_REQUEST)

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
                        teacher=staff,
                        defaults={
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

        from .models import SchoolClass
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
            from .models import SchoolClass
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
            from .models import SchoolClass
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
        
        # Check if we need to resolve school_class from class_name
        class_name = self.request.data.get("class_name")
        if not serializer.validated_data.get("school_class") and class_name:
            from .models import SchoolClass
            sc = SchoolClass.objects.filter(school=self.request.user.school, school_class=class_name).first()
            if sc:
                serializer.validated_data["school_class"] = sc

        if status_val == "VERIFIED":
            serializer.save(school=self.request.user.school, class_teacher=teacher, verified_at=timezone.now())
        else:
            serializer.save(school=self.request.user.school, class_teacher=teacher, verified_at=None)

    def perform_update(self, serializer):
        status_val = serializer.validated_data.get("status", "VERIFIED")
        
        class_name = self.request.data.get("class_name")
        if not serializer.validated_data.get("school_class") and class_name:
            from .models import SchoolClass
            sc = SchoolClass.objects.filter(school=self.request.user.school, school_class=class_name).first()
            if sc:
                serializer.validated_data["school_class"] = sc

        if status_val == "VERIFIED":
            serializer.save(verified_at=timezone.now())
        else:
            serializer.save(verified_at=None)

    @action(detail=False, methods=["get"], url_path="marks-grid")
    def marks_grid(self, request):
        year_id = request.query_params.get("academic_year")
        term_id = request.query_params.get("exam_term")
        class_id = request.query_params.get("school_class")
        class_name = request.query_params.get("class_name")
        div = request.query_params.get("division")

        from .models import Student, Result, Exam, Subject, SchoolClass, TeacherAssessmentScore

        if not class_id and class_name:
            # Fallback to finding the class_id by name
            sc = SchoolClass.objects.filter(school=request.user.school, school_class=class_name).first()
            if sc:
                class_id = sc.id

        if not year_id or not class_id:
            return Response({"error": "academic_year and school_class (or valid class_name) are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        students_qs = Student.objects.filter(school=request.user.school, school_class_id=class_id, is_active=True).order_by("roll_no", "gr_no", "id")
        if div:
            students_qs = students_qs.filter(division=div)
            
        exams_qs = Exam.objects.filter(
            school=request.user.school, 
            academic_year_id=year_id, 
            class_group_id=class_id
        ).select_related("subject", "exam_term").order_by("exam_term_id", "title", "subject__name")

        if term_id:
            exams_qs = exams_qs.filter(exam_term_id=term_id)
        if div:
            exams_qs = exams_qs.filter(division=div)

        results = list(Result.objects.filter(exam__in=exams_qs, student__in=students_qs).select_related("exam__subject"))

        # Fetch Teacher Assessment Scores
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

        # 4. Construct per-student records
        students_list = []
        for st in students_qs:
            st_full_name = " ".join([p for p in [st.surname, st.name, st.father_name] if p and str(p).strip()]) or f"Student #{st.id}"
            st_data = {
                "id": st.id,
                "name": st_full_name,
                "roll_no": st.roll_no or "",
                "gr_no": st.gr_no or "",
                "terms_marks": {},
                "teacher_assessments": {},
                "marks": {}  # Flat backwards compatibility
            }

            # Fill exam results
            st_results = [r for r in results if r.student_id == st.id]
            for r in st_results:
                ex = r.exam
                term_key = ex.exam_term.name if ex.exam_term else (ex.title.strip() if ex.title else "General Exam")
                term_id_val = str(ex.exam_term_id) if ex.exam_term_id else term_key
                if term_id_val not in st_data["terms_marks"]:
                    st_data["terms_marks"][term_id_val] = {}

                subj_id = str(ex.subject_id)
                st_data["terms_marks"][term_id_val][subj_id] = {
                    "score": float(r.marks_obtained) if r.marks_obtained is not None else None,
                    "max": float(r.max_marks),
                    "is_absent": r.is_absent
                }
                # Also populate flat marks
                st_data["marks"][subj_id] = {
                    "score": float(r.marks_obtained) if r.marks_obtained is not None else None,
                    "max": float(r.max_marks),
                    "is_absent": r.is_absent
                }

            # Fill teacher assessments
            st_tas = [ta for ta in teacher_assessments if ta.student_id == st.id]
            for ta in st_tas:
                subj_id = str(ta.subject_id)
                st_data["teacher_assessments"][subj_id] = {
                    "score": float(ta.score) if ta.score is not None else None,
                    "max_score": float(ta.max_score),
                    "remarks": ta.remarks or ""
                }

            students_list.append(st_data)

        return Response({
            "terms": terms_list,
            "teacher_assessment_subjects": list(ta_subjects_map.values()),
            "subjects": list(all_subjects_map.values()),
            "students": students_list
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
