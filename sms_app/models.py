# from xxlimited import new

from django.db import models
import uuid
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.utils.text import slugify

from django.conf import settings


class OTP(models.Model):
    email = models.EmailField(null=True, blank=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "otp"


def generate_unique_slug(model, field_value):
    base_slug = slugify(field_value)
    slug = base_slug
    counter = 1

    while model.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


class School(models.Model):

    login_id = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="schools"
    )

    name = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=50, null=True, blank=True)
    slug = models.SlugField(max_length=255, null=True, blank=True, unique=True)

    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)

    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    country = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=10, null=True, blank=True)

    is_active = models.BooleanField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "school"

    def save(self, *args, **kwargs):
        print("Name:", self.name)
        print("Slug before:", self.slug)

        if not self.slug and self.name:
            self.slug = generate_unique_slug(School, self.name)

        print("Slug after:", self.slug)

        super().save(*args, **kwargs)


# -----------SCHOLL FEATURE---------
class Feature(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        db_table = "feature"


# --------ADD SCHOOL FEATURE---------
class SchoolFeature(models.Model):
    school = models.ForeignKey("School", on_delete=models.CASCADE)
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        unique_together = ("school", "feature")
        db_table = "school_feature"


# ------------MODUL LIST------------


class Module(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)  # e.g. STUDENT, FEES
    description = models.TextField(blank=True, null=True)
    for_role = models.ForeignKey(
        Feature, on_delete=models.CASCADE, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "module"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


# -------------USER ACCESS MODUL--------


class UserModuleAccess(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="module_access"
    )

    module = models.ForeignKey(
        Module, on_delete=models.CASCADE, related_name="user_access"
    )

    class Meta:
        db_table = "user_module_access"
        unique_together = ("user", "module")
        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["module"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.module.code}"


class CustomUser(AbstractUser):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, related_name="users"
    )

    email = models.EmailField(null=True, blank=True)
    mobile = models.CharField(max_length=15, unique=True, null=True, blank=True)

    USERNAME_FIELD = "username"  # important change
    REQUIRED_FIELDS = []  #

    role = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        db_table = "custom_user"


class Staff(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    # STAFF_CATEGORIES = [
    #     ("TEACHER", "Teacher"),
    #     ("CLERK", "Clerk"),
    #     ("LIBRARIAN", "Librarian"),
    #     ("FEE MANAGEMENT", "Fee Management "),
    #     ("PRINCIPAL", "Principal"),
    #     ("TRANSOPORTATION", "Transportation "),
    #     ("INVENTORY", "Inventory "),
    # ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    name = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)
    mobile = models.CharField(max_length=15, null=True, blank=True)

    category = models.CharField(max_length=20, default="OTHER")

    address = models.TextField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    joining_date = models.DateField(auto_now_add=True)

    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.category})"

    class Meta:
        db_table = "staff"


class AcademicYear(models.Model):
    name = models.CharField(max_length=20)  # 2025-26
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    start_month = models.PositiveSmallIntegerField(null=True, blank=True)
    end_month = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    def get_start_year(self):
        if self.name and len(self.name) >= 4 and self.name[:4].isdigit():
            return int(self.name[:4])
        return None

    def get_month_numbers(self):
        if not self.start_month or not self.end_month:
            return []

        if self.start_month <= self.end_month:
            return list(range(self.start_month, self.end_month + 1))

        return list(range(self.start_month, 13)) + list(range(1, self.end_month + 1))

    def get_billing_periods(self):
        start_year = self.get_start_year()
        months = self.get_month_numbers()

        if not start_year:
            return []

        periods = []
        for month in months:
            year = start_year
            if (
                self.start_month
                and self.start_month > self.end_month
                and month < self.start_month
            ):
                year = start_year + 1
            periods.append(f"{year}-{month:02d}")

        return periods

    def __str__(self):
        return self.name

    class Meta:
        db_table = "academic_year"


class SchoolClass(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    CLASS_CHOICES = [
        ("nursery", "Nursery"),
        ("lkg", "LKG"),
        ("ukg", "UKG"),
        ("class1", "Class 1"),
        ("class2", "Class 2"),
        ("class3", "Class 3"),
        ("class4", "Class 4"),
        ("class5", "Class 5"),
        ("class6", "Class 6"),
        ("class7", "Class 7"),
        ("class8", "Class 8"),
        ("class9_basic", "Class 9 Basic Math"),
        ("class9_standard", "Class 9 Standard Math"),
        ("class9_advanced", "Class 9 Advanced Math"),
        ("class10_basic", "Class 10 Basic Math"),
        ("class10_standard", "Class 10 Standard Math"),
        ("class10_advanced", "Class 10 Advanced Math"),
        # Streams after 10
        ("class11_science", "Class 11 Science"),
        ("class11_arts", "Class 11 Arts"),
        ("class11_commerce", "Class 11 Commerce"),
        ("class12_science", "Class 12 Science"),
        ("class12_arts", "Class 12 Arts"),
        ("class12_commerce", "Class 12 Commerce"),
    ]

    school_class = models.CharField(max_length=70, choices=CLASS_CHOICES)

    def __str__(self):
        return self.school_class

    class Meta:
        db_table = "school_class"


class Division(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    SchoolClass = models.ForeignKey(SchoolClass, on_delete=models.CASCADE)
    division = models.CharField(null=True, blank=True, max_length=20)
    capacity = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.SchoolClass} ({self.division})"

    class Meta:
        db_table = "division"


class AdmissionForm(models.Model):
    school = models.ForeignKey(
        "School",
        on_delete=models.CASCADE,
        related_name="admission_forms",
        db_index=True,
    )

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.SET_NULL, null=True, blank=True
    )

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=False)
    fees_enable = models.BooleanField(default=False)

    FEE_TYPE_CHOICES = (
        ("general", "General"),
        ("individual", "Individual"),
    )

    fee_type = models.CharField(
        max_length=20, choices=FEE_TYPE_CHOICES, null=True, blank=True
    )
    fees = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    unique_link = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.school.name}"

    class Meta:
        db_table = "admission_form"


# ======newww addd======
class Admission(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE)

    form = models.ForeignKey(
        AdmissionForm, on_delete=models.SET_NULL, null=True, blank=True
    )

    temp_user = models.ForeignKey(  # IMPORTANT
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admissions",
    )
    admission_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    submitted_at = models.DateTimeField(auto_now_add=True)

    fee_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    pay_process = models.BooleanField(default=False)

    fee_verified = models.BooleanField(default=False)

    fee_verified_at = models.DateTimeField(null=True, blank=True)

    fee_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_fees",
    )

    class Meta:
        db_table = "admission"


class AdmissionFeeStructure(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    admission_form = models.ForeignKey(
        AdmissionForm, on_delete=models.CASCADE, related_name="fee_structures"
    )
    class_name = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True
    )
    fee_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    def __str__(self):
        return f"{self.class_name} - {self.fee_amount}"

    class Meta:
        db_table = "admission_fee_structure"


class FormSection(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    form = models.ForeignKey(
        "AdmissionForm", on_delete=models.CASCADE, related_name="sections"
    )
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField()

    def __str__(self):
        return self.title

    class Meta:
        db_table = "form_section"


class FormField(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    FIELD_TYPES = [
        ("text", "Text"),
        ("number", "Number"),
        # ('file', 'File'),
        ("date", "Date"),
        ("select", "Select"),
        ("checkbox", "Checkbox"),
        ("radio", "Radio"),
    ]

    section = models.ForeignKey(
        "FormSection", on_delete=models.CASCADE, related_name="fields"
    )
    label = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    options = models.JSONField(blank=True, null=True)
    order = models.PositiveIntegerField()
    # existing
    map_to_student_field = models.CharField(max_length=100, null=True, blank=True)

    # ✅ NEW
    is_system_field = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.label} ({self.field_type})"

    class Meta:
        db_table = "form_field"


# # ======newww addd======
class AdmissionFieldValue(models.Model):

    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name="field_values"
    )

    field = models.ForeignKey(FormField, on_delete=models.CASCADE)

    value = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "admission_field_value"


# # ======newww addd======
class DocumentField(models.Model):

    school = models.ForeignKey(School, on_delete=models.CASCADE)

    form = models.ForeignKey(
        AdmissionForm, on_delete=models.CASCADE, related_name="document_fields"
    )

    label = models.CharField(max_length=255)

    is_required = models.BooleanField(default=False)

    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "document_field"


# # ======newww addd======
class AdmissionDocument(models.Model):

    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)

    admission = models.ForeignKey(
        Admission, on_delete=models.CASCADE, related_name="documents"
    )

    document_field = models.ForeignKey(DocumentField, on_delete=models.CASCADE)

    file = models.FileField(upload_to="admission_documents/")

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "admission_document"


# # ======this is modified======


class Student(models.Model):

    school = models.ForeignKey(School, on_delete=models.PROTECT, db_index=True)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )

    admission = models.OneToOneField(  # VERY IMPORTANT
        "Admission", on_delete=models.SET_NULL, null=True, blank=True
    )

    # Identity
    surname = models.CharField(max_length=100, blank=True, null=True)
    name = models.CharField(max_length=100, blank=True, null=True)
    father_name = models.CharField(max_length=100, blank=True, null=True)
    mother_name = models.CharField(max_length=100, blank=True, null=True)

    date_of_birth = models.DateField(blank=True, null=True)
    mobile = models.CharField(max_length=12, blank=True, null=True)

    # Academic placement
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True
    )

    division = models.CharField(max_length=20, null=True, blank=True)

    admission_date = models.DateField(blank=True, null=True)
    gr_no = models.CharField(max_length=100, blank=True, null=True)

    academic_year = models.ForeignKey(
        "AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    aadhar_number = models.CharField(max_length=50, null=True, blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "gr_no"],
                name="unique_school_gr_no",
            )
        ]


class StudentVerify(models.Model):
    gr_no = models.CharField(max_length=50)
    admission_number = models.CharField(max_length=100, null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    clerk_verify = models.BooleanField(default=False)

    class Meta:
        db_table = "student_verify"


class StudentExtraData(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, null=True, blank=True
    )

    religion = models.CharField(max_length=100, null=True, blank=True)
    scheduled_caste = models.CharField(max_length=100, null=True, blank=True)

    place_of_birth = models.CharField(max_length=255, null=True, blank=True)

    leaving_date = models.DateField(null=True, blank=True)

    last_school = models.CharField(max_length=255, null=True, blank=True)

    progress = models.TextField(null=True, blank=True)
    conduct = models.TextField(null=True, blank=True)

    remarks = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "student_extra_data"


class TempUser(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # username = models.CharField(max_length=150, unique=True)
    # mobile_number = models.CharField(max_length=15, unique=True)
    email = models.EmailField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "temp_user"


class Parent(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_profile",
    )

    class Meta:
        db_table = "parent"


class RazorPayData(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    razorpay_key_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_secret_key = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = "razor_pay_data"


# # ======newww addd======
# class StudentStatus(models.Model):

#     STATUS_CHOICES = (
#         ("active", "Active"),
#         ("left", "Left"),
#         ("transferred", "Transferred"),
#     )

#     student = models.OneToOneField(
#         Student,
#         on_delete=models.CASCADE,
#         related_name="status"
#     )

#     status = models.CharField(
#         max_length=20,
#         choices=STATUS_CHOICES,
#         default="active"
#     )

#     leaving_date = models.DateField(null=True, blank=True)
#     leaving_reason = models.TextField(null=True, blank=True)

# # ======newww addd======
# class AdmissionVerification(models.Model):

#     admission = models.OneToOneField(
#         Admission,
#         on_delete=models.CASCADE,
#         related_name="verification"
#     )

#     principle_verified = models.BooleanField(default=False)
#     clerk_verified = models.BooleanField(default=False)
#     fees_verified = models.BooleanField(default=False)

#     principle_verified_at = models.DateTimeField(null=True, blank=True)
#     clerk_verified_at = models.DateTimeField(null=True, blank=True)
#     fees_verified_at = models.DateTimeField(null=True, blank=True)
# class StudentDocument(models.Model):

#     student = models.ForeignKey(
#         Student,
#         on_delete=models.CASCADE,
#         related_name="documents"
#     )

#     document_field = models.ForeignKey(
#         DocumentField,
#         on_delete=models.CASCADE
#     )

#     file = models.FileField(upload_to="student_documents/")

#     uploaded_at = models.DateTimeField(auto_now_add=True)


class Perents(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    perents_of = models.ForeignKey(Student, on_delete=models.CASCADE)

    class Meta:
        db_table = "parents"


class StudentFieldValue(models.Model):
    form_id = models.ForeignKey(
        AdmissionForm, on_delete=models.CASCADE, null=True, blank=True
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    student = models.ForeignKey(
        "Student", on_delete=models.CASCADE, related_name="field_values"
    )
    field = models.ForeignKey(
        "FormField", on_delete=models.CASCADE, related_name="values"
    )

    value = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.student} - {self.field.label}"

    class Meta:
        db_table = "student_field_value"


# class DocumentField(models.Model):
#     form_id = models.ForeignKey(
#         "AdmissionForm",
#         on_delete=models.CASCADE,
#         null=True,
#         blank=True,
#         related_name="label",
#     )

#     school = models.ForeignKey(
#         "School",
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name="document_fields",  # changed
#     )

#     label = models.CharField(max_length=255, null=True, blank=True)

#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.label if self.label else "Student Document"


class DocumentFile(models.Model):
    form_id = models.ForeignKey(
        "AdmissionForm", on_delete=models.CASCADE, null=True, blank=True
    )

    school = models.ForeignKey(
        "School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="document_files",  # changed
    )

    label = models.ForeignKey(
        "DocumentField", on_delete=models.CASCADE, null=True, blank=True
    )

    document = models.FileField(upload_to="student_documents/", null=True, blank=True)

    student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.label.label if self.label else "Student Document"

    class Meta:
        db_table = "document_file"


class Subject(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    name = models.CharField(max_length=100)

    division = models.ForeignKey(
        Division, on_delete=models.CASCADE, related_name="subjects"
    )

    def __str__(self):
        return f"{self.name} ({self.division})"

    class Meta:
        db_table = "subject"


class Syllabus(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    division = models.ForeignKey(
        "Division", on_delete=models.CASCADE, related_name="syllabi"
    )
    subject = models.ForeignKey(
        "Subject", on_delete=models.CASCADE, related_name="syllabi"
    )
    syllabus_file = models.FileField(upload_to="syllabus/")

    def __str__(self):
        return f"{self.division} - {self.subject}"

    class Meta:
        db_table = "syllabus"


class AdmissionFee(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    admission_number = models.CharField(max_length=100, null=True, blank=True)

    amount = models.IntegerField()
    currency = models.CharField(max_length=10, default="INR")

    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    payment_mode = models.CharField(
        max_length=100, null=True, blank=True
    )  # fill while Admission prossecc by student

    fee_verify = models.BooleanField(default=False)  # fee managment verify tanf change

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "admission_fee"


class AssignClass(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    teacher = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True
    )
    division = models.ForeignKey(
        Division, on_delete=models.CASCADE, null=True, blank=True
    )
    is_class_teacher = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.teacher} - {self.subject} - {self.division}"

    class Meta:
        db_table = "assign_class"


# ========= TIME TABLE MODEL============


class Tt_year(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    year = models.CharField(max_length=10, null=True, blank=True)

    class Meta:
        db_table = "tt_year"


class Tt_day(models.Model):
    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    year = models.ForeignKey(Tt_year, on_delete=models.CASCADE, null=True, blank=True)
    day = models.CharField(max_length=50, choices=DAY_CHOICES, null=True, blank=True)
    class_div = models.ForeignKey(
        Division, on_delete=models.CASCADE, null=True, blank=True
    )
    lecture = models.CharField(max_length=50, null=True, blank=True)

    class Meta:
        db_table = "tt_day"


class Tt_day_time(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    day = models.ForeignKey(Tt_day, on_delete=models.CASCADE, null=True, blank=True)
    start = models.TimeField(null=True, blank=True)
    end = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = "tt_day_time"


class Tt_breaks(models.Model):
    day = models.ForeignKey(Tt_day, on_delete=models.CASCADE, null=True, blank=True)
    total_breaks = models.IntegerField(null=True, blank=True)
    breaks = models.IntegerField(null=True, blank=True)
    time = models.CharField(max_length=50, null=True, blank=True)
    description = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "tt_breaks"


class Tt_slot(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    day = models.ForeignKey(Tt_day, on_delete=models.CASCADE, null=True, blank=True)
    lecture = models.CharField(max_length=50, null=True, blank=True)
    slot = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "tt_slot"


class Time_table(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    year = models.ForeignKey(Tt_year, on_delete=models.CASCADE, null=True, blank=True)
    start = models.TimeField(null=True, blank=True)
    end = models.TimeField(null=True, blank=True)
    class_div = models.ForeignKey(
        Division, on_delete=models.CASCADE, null=True, blank=True
    )
    day = models.CharField(max_length=50, null=True, blank=True)
    teacher = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)
    slot = models.CharField(max_length=50, null=True, blank=True)

    def __str__(self):
        return f"{self.year} - {self.day} - {self.class_div} - {self.slot}"

    class Meta:
        db_table = "time_table"


class AttendanceTimeRule(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    half_day_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = "attendance_time_rule"


class AttendanceLocation(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    radius = models.DecimalField(max_digits=10, decimal_places=2)
    time_rule = models.ForeignKey(AttendanceTimeRule, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"Attendance Location for {self.school}"

    class Meta:
        db_table = "attendance_location"


class Attendance(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=20, null=True, blank=True)
    attendance_date = models.DateField(default=timezone.localdate, db_index=True)
    date_time = models.DateTimeField(null=True, blank=True)
    is_present = models.BooleanField(default=False)
    is_half_day = models.BooleanField(default=False)

    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "attendance"
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "attendance_date"],
                name="unique_staff_attendance_per_day",
            )
        ]

        indexes = [
            models.Index(
                fields=["school", "attendance_date"],
                name="attendance_school_date_idx",
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.attendance_date}"
    
    

class LeaveType(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = "leave_type"


class LeaveTemplate(models.Model):
    # TIMELINE_CHOICES = [
    #     ("MONTHLY", "Monthly"),
    #     ("QUARTERLY", "Quarterly"),
    #     ("SEMI_ANNUAL", "Semi-Annual"),
    #     ("ANNUAL", "Annual"),
    # ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    # time_line = models.CharField(
    #     max_length=20, choices=TIMELINE_CHOICES, null=True, blank=True
    # )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, null=True)
    leave_num = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    time_line = models.CharField(max_length=20,default="MONTHLY")

    def __str__(self):
        return f"{self.staff.name} - {self.leave_type}"

    class Meta:
        db_table = "leave_template"
        
        constraints = [
            models.UniqueConstraint(
                fields=["school", "staff", "leave_type"],
                name="unique_staff_leave_type"
            )
        ]


class LeaveRequest(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)
    # leave_type = models.CharField(max_length=100, null=True, blank=True)
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    total_days = models.IntegerField(null=True, blank=True)
    reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(
        auto_now=True, null=True, blank=True
    )  # at a time no nedd this

    def __str__(self):
        # return f"{self.staff.name} - {self.leave_type} - {self.status}"
        return f"{self.staff.name} - {self.leave_type} - {self.total_days} "

    class Meta:
        db_table = "leave_request"


class LeavePerDay(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )

    leave = models.ForeignKey(
        LeaveRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="leave_days",
    )
    date = models.DateField(null=True, blank=True)

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ]

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="PENDING", null=True, blank=True
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.date} - {self.leave.total_days} leaves"

    class Meta:
        db_table = "leave_per_day"


class StaffRemainingLeave(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)
    leave_template = models.ForeignKey(
        LeaveTemplate, on_delete=models.CASCADE, null=True, blank=True
    )
    total_levaes = models.IntegerField(null=True, blank=True)
    remaining_leaves = models.IntegerField(null=True, blank=True)
    
    month = models.IntegerField(default=timezone.now().month)
    
    year = models.IntegerField(default=timezone.now().year)

    def __str__(self):
        return f"{self.staff} - {self.leave_template}"
    
    # def apply_carry_forward(self):
    #     self.remaining_leaves += self.leave_template.leave_num
    #     self.save()

    class Meta:
        db_table = "staff_remaining_leave"
        
        # constraints = [
        #     models.UniqueConstraint(
        #         fields=["staff", "leave_template", "month", "year"],
        #         name="unique_staff_leave_month_year"
        #     )
        # ]


class Announcement(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    title = models.CharField(max_length=255)
    description = models.TextField()

    publish_at = models.DateTimeField()  # when it becomes visible
    expires_at = models.DateTimeField(null=True, blank=True)  # optional

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "announcement"


class AnnouncementTarget(models.Model):
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, db_index=True
    )
    TARGET_TYPE = [
        ("ALL", "All"),
        ("ROLE", "Role"),
        ("CLASS", "Class"),
        ("SPECIFIC", "Specific User"),
    ]

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="targets"
    )

    target_type = models.CharField(max_length=10, choices=TARGET_TYPE)
    target_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "announcement_target"


# =============FEE MANAGEMENT TABLE=================


class FeeType(models.Model):
    BILLING_CHOICES = [
        ("single", "Single"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("half_yearly", "Half-Yearly"),
        ("yearly", "Yearly"),
    ]
    name = models.CharField(
        max_length=100, null=True, blank=True
    )  # Tuition, Transport, Exam
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    billing_cycle = models.CharField(
        max_length=20, choices=BILLING_CHOICES, null=True, blank=True
    )

    def __str__(self):
        return self.name or "Fee Type"

    class Meta:
        db_table = "fee_type"


class FeeWiseClass(models.Model):
    LATE_FEE_TYPE_CHOICES = [
        ("fixed", "Fixed"),
        ("per_day", "Per Day"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    feetype = models.ForeignKey(
        FeeType, on_delete=models.CASCADE, null=True, blank=True
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE, null=True, blank=True
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    late_fee_enabled = models.BooleanField(default=False)
    grace_days = models.PositiveIntegerField(default=0)
    late_fee_type = models.CharField(
        max_length=20, choices=LATE_FEE_TYPE_CHOICES, null=True, blank=True
    )
    late_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_late_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    def __str__(self):
        return f"{self.feetype} - {self.school_class} - {self.amount}"

    class Meta:
        db_table = "fee_wise_class"


class StudentFee(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("partial", "Partial"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]
    LATE_FEE_TYPE_CHOICES = [
        ("fixed", "Fixed"),
        ("per_day", "Per Day"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, null=True, blank=True
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="student_fees"
    )
    feetype = models.ForeignKey(FeeType, on_delete=models.CASCADE)
    fee_wise_class = models.ForeignKey(
        FeeWiseClass, on_delete=models.SET_NULL, null=True, blank=True
    )

    billing_period = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Example: 2026-04 for monthly, Q1 for quarterly, or blank for single fees.",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_reference = models.CharField(max_length=255, null=True, blank=True)
    discount_note = models.TextField(null=True, blank=True)
    late_fee_enabled = models.BooleanField(default=False)
    grace_days = models.PositiveIntegerField(default=0)
    late_fee_type = models.CharField(
        max_length=20, choices=LATE_FEE_TYPE_CHOICES, null=True, blank=True
    )
    late_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_late_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payment_mode = models.CharField(max_length=100, null=True, blank=True)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "student_fee"
        unique_together = ("student", "feetype", "academic_year", "billing_period")

    @property
    def payable_amount(self):
        base_amount = self.amount or 0
        return base_amount + self.fine_amount - self.discount_amount

    @property
    def balance_amount(self):
        return self.payable_amount - self.paid_amount

    def calculate_late_fee(self, today=None):
        from datetime import timedelta
        from django.utils import timezone

        if (
            not self.late_fee_enabled
            or not self.due_date
            or self.status in ["paid", "cancelled"]
        ):
            return 0

        today = today or timezone.localdate()
        penalty_start_date = self.due_date + timedelta(days=self.grace_days)

        if today <= penalty_start_date:
            return 0

        if self.late_fee_type == "fixed":
            late_fee = self.late_fee_amount
        elif self.late_fee_type == "per_day":
            late_days = (today - penalty_start_date).days
            late_fee = self.late_fee_amount * late_days
        else:
            late_fee = 0

        if self.max_late_fee is not None:
            late_fee = min(late_fee, self.max_late_fee)

        return late_fee

    def apply_late_fee(self, today=None, save=True):
        self.fine_amount = self.calculate_late_fee(today=today)
        if save:
            self.save(update_fields=["fine_amount"])
        return self.fine_amount

    def refresh_payment_status(self):
        from django.db.models import Sum
        from django.utils import timezone

        total_paid = (
            self.payments.filter(is_verified=True).aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        self.paid_amount = total_paid

        if total_paid <= 0:
            self.status = "pending"
            self.paid_at = None
        elif total_paid >= self.payable_amount:
            self.status = "paid"
            self.paid_at = timezone.now()
        else:
            self.status = "partial"
            self.paid_at = None

        latest_payment = (
            self.payments.filter(is_verified=True)
            .order_by("-payment_date", "-created_at")
            .first()
        )
        if latest_payment:
            self.payment_mode = latest_payment.payment_mode
            self.transaction_id = latest_payment.transaction_id
        else:
            self.payment_mode = None
            self.transaction_id = None

        self.save(
            update_fields=[
                "paid_amount",
                "status",
                "paid_at",
                "payment_mode",
                "transaction_id",
            ]
        )

    def save(self, *args, **kwargs):
        if self.fee_wise_class:
            self.feetype = self.fee_wise_class.feetype
            if self.amount is None:
                self.amount = self.fee_wise_class.amount
            if not self.pk:
                self.late_fee_enabled = self.fee_wise_class.late_fee_enabled
                self.grace_days = self.fee_wise_class.grace_days
                self.late_fee_type = self.fee_wise_class.late_fee_type
                self.late_fee_amount = self.fee_wise_class.late_fee_amount
                self.max_late_fee = self.fee_wise_class.max_late_fee
            if not self.school:
                self.school = self.fee_wise_class.school

        if self.student and not self.school:
            self.school = self.student.school

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.feetype} - {self.billing_period or 'single'}"


class StudentFeePayment(models.Model):
    PAYMENT_MODE_CHOICES = [
        ("cash", "Cash"),
        ("online", "Online"),
        ("cheque", "Cheque"),
        ("bank_transfer", "Bank Transfer"),
        ("upi", "UPI"),
    ]

    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True, blank=True)
    student_fee = models.ForeignKey(
        StudentFee, on_delete=models.CASCADE, related_name="payments"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="fee_payments"
    )
    feetype = models.ForeignKey(FeeType, on_delete=models.CASCADE)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE_CHOICES)
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)
    receipt_number = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="collected_fee_payments",
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_student_fee_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_fee_payment"

    def save(self, *args, **kwargs):
        if self.student_fee:
            self.school = self.student_fee.school
            self.student = self.student_fee.student
            self.feetype = self.student_fee.feetype

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.feetype} - {self.amount}"


# ---------TABLES FOR SALARY--------


class SalaryComponent(models.Model):
    COMPONENT_TYPE = (
        ("earning", "Earning"),
        ("deduction", "Deduction"),
    )

    name = models.CharField(max_length=255)  # DA, HRA, PF
    component_type = models.CharField(max_length=20, choices=COMPONENT_TYPE)
    is_active = models.BooleanField(default=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE)

    class Meta:
        db_table = "salary_component"


class StaffSalaryComponent(models.Model):

    CALCULATION_TYPE = (
        ("fixed", "Fixed"),
        ("percentage", "Percentage"),
    )

    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="salary_components"
    )
    component = models.ForeignKey(SalaryComponent, on_delete=models.CASCADE)

    calculation_type = models.CharField(max_length=20, choices=CALCULATION_TYPE)
    value = models.DecimalField(max_digits=20, decimal_places=2)

    # optional
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "staff_salary_component"


class StaffSalaryPayment(models.Model):
    PAYMENT_MODE = (
        ("online", "Online"),
        ("offline", "Offline"),
    )

    PAYMENT_STATUS = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, db_index=True)
    staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="salary_payments"
    )

    staff_name = models.CharField(max_length=255, null=True, blank=True)
    staff_category = models.CharField(max_length=100, null=True, blank=True)
    salary_month = models.CharField(
        max_length=7,
        help_text="Salary month in YYYY-MM format.",
    )

    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    working_days = models.PositiveIntegerField(default=0)
    present_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    absent_days = models.PositiveIntegerField(default=0)
    half_days = models.PositiveIntegerField(default=0)
    attendance_deduction = models.DecimalField(
        max_digits=12, decimal_places=2, default=0
    )
    component_snapshot = models.JSONField(default=list, blank=True)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2)

    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODE)
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default="paid"
    )
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    receipt_number = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)

    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_salary_payments",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "staff_salary_payment"
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "salary_month"],
                name="unique_staff_salary_payment_per_month",
            )
        ]
        indexes = [
            models.Index(
                fields=["school", "salary_month"],
                name="sal_pay_school_month_idx",
            )
        ]

    def save(self, *args, **kwargs):
        if self.staff:
            self.school = self.staff.school
            self.staff_name = self.staff.name
            self.staff_category = self.staff.category

        super().save(*args, **kwargs)


#  ITS FOR TIME TABLE
# =========================================================
# WORKING DAYS
# =========================================================


class WorkingDay(models.Model):

    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    ]

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="working_days"
    )

    day = models.CharField(max_length=20, choices=DAY_CHOICES)

    class Meta:
        db_table = "working_day"
        unique_together = ("school", "day")

    def __str__(self):
        return f"{self.school.name} - {self.day}"


# =========================================================
# HOLIDAYS
# =========================================================


class Holiday(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="holidays"
    )

    name = models.CharField(max_length=255)

    start_date = models.DateField()

    end_date = models.DateField(null=True, blank=True)

    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "holiday"

    def __str__(self):
        return self.name


# THIS MODEL ALL REDAY HAVE

# =========================================================
# STANDARD / CLASS
# =========================================================

# =========================================================
# SUBJECT
# =========================================================

# =========================================================
# TEACHER
# =========================================================


# =========================================================
# TIMETABLE
# =========================================================


class Timetable(models.Model):

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="timetables"
    )

    class_div = models.ForeignKey(
        Division, on_delete=models.CASCADE, related_name="timetables"
    )

    academic_year = models.ForeignKey(
        "AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    total_lectures = models.PositiveIntegerField(default=0)

    total_breaks = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "timetable"
        unique_together = ("school", "class_div", "academic_year")

    def __str__(self):
        return f"{self.standard} - {self.academic_year}"


# =========================================================
# LECTURE SLOT
# =========================================================


class LectureSlot(models.Model):
    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, null=True, blank=True
    )

    timetable = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, related_name="lecture_slots"
    )

    lecture_number = models.PositiveIntegerField()

    start_time = models.TimeField()

    end_time = models.TimeField()

    class Meta:
        db_table = "lecture_slot"
        ordering = ["lecture_number"]

        unique_together = ("timetable", "lecture_number")

    def __str__(self):
        return f"Lecture {self.lecture_number}"


# =========================================================
# BREAK SLOT
# =========================================================


class BreakSlot(models.Model):
    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, null=True, blank=True
    )

    timetable = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, related_name="break_slots"
    )

    break_number = models.PositiveIntegerField()

    start_time = models.TimeField()

    end_time = models.TimeField()

    duration_minutes = models.PositiveIntegerField()

    class Meta:
        db_table = "break_slot"
        ordering = ["break_number"]

        unique_together = ("timetable", "break_number")

    def __str__(self):
        return f"Break {self.break_number}"


# =========================================================
# TIMETABLE ENTRY
# =========================================================


class TimetableEntry(models.Model):
    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, null=True, blank=True
    )

    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    ]

    timetable = models.ForeignKey(
        Timetable, on_delete=models.CASCADE, related_name="entries"
    )

    day = models.CharField(max_length=20, choices=DAY_CHOICES)

    lecture_slot = models.ForeignKey(
        LectureSlot, on_delete=models.CASCADE, related_name="entries"
    )

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name="timetable_entries"
    )

    teacher_staff = models.ForeignKey(
        Staff, on_delete=models.CASCADE, related_name="timetable_entries"
    )

    class Meta:
        db_table = "timetable_entry"
        unique_together = ("timetable", "day", "lecture_slot")

    def __str__(self):
        return f"{self.day} - " f"{self.subject.name} - " f"{self.teacher_staff.name}"


from django.core.exceptions import ValidationError


class Time_Table_tb(models.Model):
    school = models.ForeignKey("School", on_delete=models.CASCADE)

    DAY_CHOICES = [
        ("monday", "Monday"),
        ("tuesday", "Tuesday"),
        ("wednesday", "Wednesday"),
        ("thursday", "Thursday"),
        ("friday", "Friday"),
        ("saturday", "Saturday"),
        ("sunday", "Sunday"),
    ]

    day = models.CharField(max_length=20, choices=DAY_CHOICES)

    class_division = models.ForeignKey(Division, on_delete=models.CASCADE)

    total_lecture = models.PositiveIntegerField()

    start_time = models.TimeField()

    end_time = models.TimeField()

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("End time must be greater than start time")

    class Meta:
        db_table = "time_table_tb"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "class_division", "day"], name="unique_division_day"
            )
        ]


class Slot(models.Model):
    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, null=True, blank=True
    )

    timetable = models.ForeignKey(
        Time_Table_tb, on_delete=models.CASCADE, related_name="slots"
    )

    is_lecture = models.BooleanField(default=False)
    is_break = models.BooleanField(default=False)
    slot_number = models.PositiveIntegerField()

    slot_start_time = models.TimeField(null=True, blank=True)

    slot_end_time = models.TimeField(null=True, blank=True)

    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, null=True, blank=True
    )

    teacher = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        db_table = "slot"
        ordering = ["slot_number"]

        unique_together = ("timetable", "slot_number")

    def clean(self):
        if self.is_lecture == self.is_break:
            raise ValidationError("Slot must be either lecture or break")

    def __str__(self):
        return f"Lecture {self.slot_number}"


from django.db import models


class StudentAttendance(models.Model):

    school = models.ForeignKey(
        "School",
        on_delete=models.CASCADE,
        related_name="student_attendance",
    )

    student = models.ForeignKey(
        "Student",
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )

    attendance_by = models.ForeignKey(
        "Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taken_attendance",
    )

    is_present = models.BooleanField(default=False)

    is_absent = models.BooleanField(default=False)

    attendance_date = models.DateField(auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "student_attendance"
        unique_together = ("student", "attendance_date")

    def __str__(self):
        return f"{self.student} - {self.attendance_date}"


class Homework(models.Model):

    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, related_name="homeworks"
    )

    division = models.ForeignKey(
        "Division", on_delete=models.CASCADE, related_name="homeworks"
    )

    teacher = models.ForeignKey(
        "Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_homeworks",
    )

    title = models.CharField(max_length=255)

    description = models.TextField()

    assigned_date = models.DateField(auto_now_add=True)

    due_date = models.DateField()

    attachment = models.FileField(upload_to="homework/", null=True, blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "homework"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title}"


class HomeworkSubmission(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("submitted", "Submitted"),
        ("late", "Late Submission"),
        ("checked", "Checked"),
    ]

    school = models.ForeignKey(
        "School", on_delete=models.CASCADE, related_name="homework_submissions"
    )

    homework = models.ForeignKey(
        "Homework", on_delete=models.CASCADE, related_name="submissions"
    )

    student = models.ForeignKey(
        "Student", on_delete=models.CASCADE, related_name="homework_submissions"
    )

    attachment = models.FileField(
        upload_to="homework/submissions/", null=True, blank=True
    )

    submitted_at = models.DateTimeField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    teacher_remark = models.TextField(null=True, blank=True)

    checked_by = models.ForeignKey(
        "Staff",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="checked_homeworks",
    )

    checked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "homework_submission"
        unique_together = ["homework", "student"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student}"
    
    
class CertificateType(models.Model):
    name = models.CharField(max_length=100, null=True, blank=True)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = "certificate_type"
    
    
    
class CertificateRequest(models.Model):
    # student = models.ForeignKey(Student, on_delete=models.CASCADE)
    certificate_type = models.ForeignKey(CertificateType, on_delete=models.CASCADE)
    school = models.ForeignKey(School, on_delete=models.CASCADE, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("APPROVED", "Approved"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "certificate_request"
        
# class Certificate(models.Model):
#     student = 
    


# # Ensure every model in this app uses a consistent db_table naming convention
# # without modifying individual model Meta classes or fields.
# try:
#     from django.apps import apps

#     for _model in apps.get_models():
#         if getattr(_model._meta, "app_label", None) == "sms_app":
#             # set table name to '<modelname>_table' (model_name is already lowercase)
#             _model._meta.db_table = f"{_model._meta.model_name}_table"
# except Exception:
#     # import-time may fail in some management commands; ignore silently
#     pass
