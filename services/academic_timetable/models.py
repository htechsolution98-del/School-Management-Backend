from django.db import models


class AcademicYear(models.Model):
    year_label = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)

    class Meta:
        db_table = "academic_timetable_year"

    def __str__(self):
        return self.year_label


class ClassCategory(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        db_table = "academic_class_category"

    def __str__(self):
        return self.name


class SchoolClass(models.Model):
    category = models.ForeignKey(ClassCategory, on_delete=models.CASCADE, null=True, blank=True)
    class_name = models.CharField(max_length=100)

    class Meta:
        db_table = "academic_school_class"

    def __str__(self):
        return self.class_name


class Division(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name="divisions")
    division_name = models.CharField(max_length=50)

    class Meta:
        db_table = "academic_division"

    def __str__(self):
        return f"{self.school_class.class_name} - {self.division_name}"


class Subject(models.Model):
    subject_name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = "academic_subject"

    def __str__(self):
        return self.subject_name


class Syllabus(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "academic_syllabus"


class StudyMaterial(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file_path = models.FileField(upload_to="study_materials/")

    class Meta:
        db_table = "academic_study_material"


class Timetable(models.Model):
    division = models.ForeignKey(Division, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)

    class Meta:
        db_table = "academic_timetable_entry"
