from django.db import models
from django.conf import settings


class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = "staff_department"

    def __str__(self):
        return self.name


class Staff(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_hr_profile")
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    employee_id = models.CharField(max_length=50, unique=True)
    staff_name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, default="TEACHER")

    class Meta:
        db_table = "staff_profile"

    def __str__(self):
        return f"{self.staff_name} ({self.employee_id})"


class StaffFace(models.Model):
    staff = models.OneToOneField(Staff, on_delete=models.CASCADE, related_name="face_data")
    encoding = models.TextField()

    class Meta:
        db_table = "staff_face_biometric"


class LeaveTemplate(models.Model):
    name = models.CharField(max_length=100)
    time_line = models.CharField(max_length=50, default="MONTHLY")

    class Meta:
        db_table = "staff_leave_template"


class LeaveType(models.Model):
    leave_template = models.ForeignKey(LeaveTemplate, on_delete=models.CASCADE, related_name="types")
    name = models.CharField(max_length=100)
    leave_num = models.IntegerField(default=1)
    is_carry_forward = models.BooleanField(default=False)

    class Meta:
        db_table = "staff_leave_type"


class LeaveRequest(models.Model):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=50, default="PENDING")
    reason = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "staff_leave_request"
