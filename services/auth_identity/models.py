from django.db import models
from django.contrib.auth.models import AbstractUser


class OTP(models.Model):
    mobile_or_email = models.CharField(max_length=255)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "auth_otp"

    def __str__(self):
        return f"{self.mobile_or_email} - {self.otp}"


class UserModuleAccess(models.Model):
    user = models.ForeignKey("auth_identity.CustomUser", on_delete=models.CASCADE, related_name="auth_module_accesses")
    module = models.ForeignKey("tenant_subscription.Module", on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auth_user_module_access"
        unique_together = ("user", "module")


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ("SUPERADMIN", "Super Admin"),
        ("PRINCIPAL", "Principal"),
        ("TEACHER", "Teacher"),
        ("STUDENT", "Student"),
        ("PARENT", "Parent"),
        ("CLERK", "Clerk"),
        ("LIBRARIAN", "Librarian"),
        ("FEEMANAGER", "Fee Manager"),
    )

    school = models.ForeignKey("tenant_subscription.School", on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default="STUDENT")
    mobile = models.CharField(max_length=15, blank=True, null=True)

    groups = models.ManyToManyField(
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to.",
        related_name="auth_identity_user_set",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission",
        verbose_name="user permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_name="auth_identity_user_set",
        related_query_name="user",
    )

    class Meta:
        db_table = "auth_custom_user"


class TempUser(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    mobile = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "auth_temp_user"
