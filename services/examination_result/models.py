from django.db import models


class ExamTerm(models.Model):
    title = models.CharField(max_length=100)
    academic_year = models.ForeignKey("academic_timetable.AcademicYear", on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "service_exam_term"

    def __str__(self):
        return self.title


class ExamRoom(models.Model):
    room_number = models.CharField(max_length=50)
    capacity = models.IntegerField(default=30)

    class Meta:
        db_table = "service_exam_room"


class Exam(models.Model):
    term = models.ForeignKey(ExamTerm, on_delete=models.CASCADE, related_name="exams")
    subject = models.ForeignKey("academic_timetable.Subject", on_delete=models.CASCADE)
    school_class = models.ForeignKey("academic_timetable.SchoolClass", on_delete=models.CASCADE)
    exam_date = models.DateField()
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)

    class Meta:
        db_table = "exam_schedule"


class Result(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="results")
    student = models.ForeignKey("student_admission.Student", on_delete=models.CASCADE)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        db_table = "exam_result"


class ResultWeightageConfig(models.Model):
    term = models.ForeignKey(ExamTerm, on_delete=models.CASCADE)
    weightage_percent = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)

    class Meta:
        db_table = "exam_result_weightage_config"
