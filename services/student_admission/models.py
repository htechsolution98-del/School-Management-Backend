from django.db import models


class AdmissionForm(models.Model):
    title = models.CharField(max_length=255)
    academic_year = models.ForeignKey("academic_timetable.AcademicYear", on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_admission_form"


class FormSection(models.Model):
    form = models.ForeignKey(AdmissionForm, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=100)
    order = models.IntegerField(default=1)

    class Meta:
        db_table = "student_form_section"


class FormField(models.Model):
    section = models.ForeignKey(FormSection, on_delete=models.CASCADE, related_name="fields")
    label = models.CharField(max_length=100)
    field_type = models.CharField(max_length=50)
    is_required = models.BooleanField(default=False)

    class Meta:
        db_table = "student_form_field"


class Student(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    gr_no = models.CharField(max_length=50, unique=True)
    dob = models.DateField()
    gender = models.CharField(max_length=20)
    school_class = models.ForeignKey("academic_timetable.SchoolClass", on_delete=models.SET_NULL, null=True)
    division = models.ForeignKey("academic_timetable.Division", on_delete=models.SET_NULL, null=True)

    class Meta:
        db_table = "student_profile"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.gr_no})"


class Perents(models.Model):
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name="parent_info")
    father_name = models.CharField(max_length=100)
    mother_name = models.CharField(max_length=100)
    father_mobile = models.CharField(max_length=15)
    mother_mobile = models.CharField(max_length=15, blank=True, null=True)

    class Meta:
        db_table = "student_parent_info"


class StudentDocument(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=100)
    file = models.FileField(upload_to="student_docs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_student_document"
