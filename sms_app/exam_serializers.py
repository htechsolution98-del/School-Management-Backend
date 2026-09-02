from rest_framework import serializers
from sms_app.models import (
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
    Student,
    Subject,
    SchoolClass,
    AcademicYear,
)

class ResultWeightageComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultWeightageComponent
        fields = ["id", "config", "name", "component_type", "weightage_percentage", "sequence"]

class ResultWeightageConfigSerializer(serializers.ModelSerializer):
    components = ResultWeightageComponentSerializer(many=True, read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    total_weightage = serializers.SerializerMethodField()

    class Meta:
        model = ResultWeightageConfig
        fields = [
            "id",
            "school",
            "academic_year",
            "academic_year_name",
            "title",
            "status",
            "is_active",
            "is_locked",
            "components",
            "total_weightage",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["school"]

    def get_total_weightage(self, obj):
        return sum([float(c.weightage_percentage) for c in obj.components.all()])


class ExamRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExamRoom
        fields = ["id", "school", "room_number", "building_block", "capacity", "is_active"]
        read_only_fields = ["school"]


class ExamTermSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    component_name = serializers.CharField(source="weightage_component.name", read_only=True, default="")

    class Meta:
        model = ExamTerm
        fields = [
            "id",
            "school",
            "academic_year",
            "academic_year_name",
            "weightage_component",
            "component_name",
            "name",
            "code",
            "max_marks",
            "passing_marks",
            "instructions",
        ]
        read_only_fields = ["school"]


class ExamFullSerializer(serializers.ModelSerializer):
    exam_date = serializers.DateField(input_formats=["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "iso-8601"])
    subject_name = serializers.CharField(source="subject.name", read_only=True, default="")
    class_name = serializers.CharField(source="class_group.school_class", read_only=True, default="")
    room_number = serializers.CharField(source="room.room_number", read_only=True, default="")
    term_name = serializers.CharField(source="exam_term.name", read_only=True, default="")

    class Meta:
        model = Exam
        fields = [
            "id",
            "school",
            "academic_year",
            "exam_term",
            "term_name",
            "created_by",
            "title",
            "description",
            "subject",
            "subject_name",
            "class_group",
            "class_name",
            "division",
            "exam_date",
            "start_time",
            "end_time",
            "duration_minutes",
            "room",
            "room_number",
            "max_marks",
            "passing_marks",
            "status",
            "created_at",
        ]
        read_only_fields = ["school", "created_by"]


class SeatingAllocationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    roll_no = serializers.CharField(source="student.roll_no", read_only=True, default="")
    gr_no = serializers.CharField(source="student.gr_no", read_only=True, default="")
    exam_title = serializers.CharField(source="exam.title", read_only=True, default="")
    room_number = serializers.CharField(source="room.room_number", read_only=True, default="")
    class_name = serializers.CharField(source="exam.class_group.name", read_only=True, default="")
    division = serializers.CharField(source="exam.division", read_only=True, default="")
    subject_name = serializers.CharField(source="exam.subject.name", read_only=True, default="")

    class Meta:
        model = SeatingAllocation
        fields = [
            "id",
            "exam",
            "exam_title",
            "class_name",
            "division",
            "subject_name",
            "student",
            "student_name",
            "roll_no",
            "gr_no",
            "room",
            "room_number",
            "seat_number",
            "is_published",
            "created_at",
        ]

    def get_student_name(self, obj):
        return f"{obj.student.surname or ''} {obj.student.name or ''}".strip() or f"Student #{obj.student.id}"


class SubjectMarksEntrySerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    roll_no = serializers.CharField(source="student.roll_no", read_only=True, default="")
    gr_no = serializers.CharField(source="student.gr_no", read_only=True, default="")

    class Meta:
        model = Result
        fields = [
            "id",
            "exam",
            "student",
            "student_name",
            "roll_no",
            "gr_no",
            "entered_by",
            "marks_obtained",
            "max_marks",
            "is_absent",
            "grade",
            "remarks",
            "status",
            "is_published",
            "updated_at",
        ]

    def get_student_name(self, obj):
        return f"{obj.student.surname or ''} {obj.student.name or ''}".strip() or f"Student #{obj.student.id}"


class TeacherAssessmentScoreSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    teacher_name = serializers.CharField(source="teacher.name", read_only=True, default="")

    class Meta:
        model = TeacherAssessmentScore
        fields = [
            "id",
            "school",
            "academic_year",
            "student",
            "student_name",
            "teacher",
            "teacher_name",
            "subject",
            "is_class_teacher",
            "score",
            "max_score",
            "remarks",
            "updated_at",
        ]
        read_only_fields = ["school", "teacher"]

    def get_student_name(self, obj):
        return f"{obj.student.surname or ''} {obj.student.name or ''}".strip() or f"Student #{obj.student.id}"


class ClassTeacherMarksVerificationSerializer(serializers.ModelSerializer):
    class_name = serializers.CharField(source="school_class.school_class", read_only=True, default="")
    teacher_name = serializers.CharField(source="class_teacher.name", read_only=True, default="")

    class Meta:
        model = ClassTeacherMarksVerification
        fields = [
            "id",
            "school",
            "academic_year",
            "exam_term",
            "school_class",
            "class_name",
            "division",
            "class_teacher",
            "teacher_name",
            "status",
            "remarks",
            "verified_at",
        ]
        read_only_fields = ["school", "class_teacher"]


class FinalStudentResultSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    roll_no = serializers.CharField(source="student.roll_no", read_only=True, default="")
    gr_no = serializers.CharField(source="student.gr_no", read_only=True, default="")
    class_name = serializers.CharField(source="school_class.school_class", read_only=True, default="")
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True, default="")
    percentage = serializers.DecimalField(source="total_percentage", max_digits=5, decimal_places=2, read_only=True)
    total_marks_obtained = serializers.SerializerMethodField()
    total_max_marks = serializers.SerializerMethodField()

    class Meta:
        model = FinalStudentResult
        fields = [
            "id",
            "school",
            "academic_year",
            "academic_year_name",
            "student",
            "student_name",
            "roll_no",
            "gr_no",
            "school_class",
            "class_name",
            "division",
            "component_breakdown",
            "total_percentage",
            "percentage",
            "total_marks_obtained",
            "total_max_marks",
            "grade",
            "remarks",
            "status",
            "is_published",
            "published_at",
            "updated_at",
        ]
        read_only_fields = ["school"]

    def get_student_name(self, obj):
        parts = [obj.student.surname, obj.student.name, obj.student.father_name]
        return " ".join([p for p in parts if p and str(p).strip()]) or f"Student #{obj.student.id}"

    def get_total_marks_obtained(self, obj):
        breakdown = obj.component_breakdown or {}
        components = breakdown.get("components", [])
        total_obtained = 0.0
        has_marks = False
        for c in components:
            details = c.get("details", "")
            if "Marks: " in details:
                try:
                    marks_str = details.split("Marks: ")[1].split("/")[0]
                    total_obtained += float(marks_str)
                    has_marks = True
                except Exception:
                    pass
        if has_marks:
            return round(total_obtained, 1)
        # fallback: from all student results
        from .models import Result
        res = Result.objects.filter(student=obj.student, exam__academic_year=obj.academic_year)
        if res.exists():
            return round(sum([float(r.marks_obtained or 0) for r in res if not r.is_absent]), 1)
        return "—"

    def get_total_max_marks(self, obj):
        breakdown = obj.component_breakdown or {}
        components = breakdown.get("components", [])
        total_max = 0.0
        has_marks = False
        for c in components:
            details = c.get("details", "")
            if "Marks: " in details:
                try:
                    marks_str = details.split("Marks: ")[1].split("/")[1]
                    total_max += float(marks_str)
                    has_marks = True
                except Exception:
                    pass
        if has_marks:
            return round(total_max, 1)
        # fallback: from all student results
        from .models import Result
        res = Result.objects.filter(student=obj.student, exam__academic_year=obj.academic_year)
        if res.exists():
            return round(sum([float(r.max_marks or 100) for r in res]), 1)
        return "—"
