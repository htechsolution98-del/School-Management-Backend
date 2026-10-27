from django.db import models
from django.conf import settings
from django.utils import timezone
from .models import School, Student, Staff


class IDCardTemplate(models.Model):
    USER_TYPE_CHOICES = (
        ('STUDENT', 'Student'),
        ('STAFF', 'Staff / Teacher'),
    )
    ORIENTATION_CHOICES = (
        ('PORTRAIT', 'Portrait (Vertical)'),
        ('LANDSCAPE', 'Landscape (Horizontal)'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='id_card_templates', db_index=True)
    name = models.CharField(max_length=150)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='STUDENT')
    orientation = models.CharField(max_length=20, choices=ORIENTATION_CHOICES, default='PORTRAIT')

    front_background = models.ImageField(upload_to='id_cards/templates/front/', null=True, blank=True)
    back_background = models.ImageField(upload_to='id_cards/templates/back/', null=True, blank=True)

    # layout_config stores array of fields with x, y, width, height, side (front/back), visible, style, and lanyard safe zone settings
    layout_config = models.JSONField(default=dict, blank=True)

    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'id_card_template'
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.get_user_type_display()} - {self.orientation})"


class IDCardRecord(models.Model):
    STATUS_CHOICES = (
        ('NOT_GENERATED', 'Not Generated'),
        ('ISSUED', 'Issued'),
        ('REISSUED', 'Reissued'),
        ('EXPIRED', 'Expired'),
        ('LOST_DAMAGED', 'Lost / Damaged'),
    )
    USER_TYPE_CHOICES = (
        ('STUDENT', 'Student'),
        ('STAFF', 'Staff / Teacher'),
    )

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='id_card_records', db_index=True)
    template = models.ForeignKey(IDCardTemplate, on_delete=models.PROTECT, related_name='records')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='STUDENT')

    student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True, related_name='id_card_records')
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, null=True, blank=True, related_name='id_card_records')

    card_number = models.CharField(max_length=60, unique=True, db_index=True)
    card_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED')

    issue_date = models.DateField(default=timezone.now)
    valid_upto = models.DateField(null=True, blank=True)

    blood_group = models.CharField(max_length=10, blank=True, null=True)
    emergency_contact = models.CharField(max_length=25, blank=True, null=True)

    custom_field_1_value = models.CharField(max_length=150, blank=True, null=True)
    custom_field_2_value = models.CharField(max_length=150, blank=True, null=True)
    custom_field_3_value = models.CharField(max_length=150, blank=True, null=True)

    version = models.PositiveIntegerField(default=1)
    reissue_reason = models.CharField(max_length=255, null=True, blank=True)
    previous_card = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='reissue_history')

    snapshot_data = models.JSONField(default=dict, blank=True)

    front_image = models.ImageField(upload_to='id_cards/generated/front/', null=True, blank=True)
    back_image = models.ImageField(upload_to='id_cards/generated/back/', null=True, blank=True)
    pdf_file = models.FileField(upload_to='id_cards/generated/pdf/', null=True, blank=True)

    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'id_card_record'
        ordering = ['-issue_date', '-created_at']

    def __str__(self):
        target = f"{self.student.name} {self.student.surname}" if self.student else (self.staff.name if self.staff else "Unknown")
        return f"{self.card_number} - {target} (v{self.version})"


class IDCardLog(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='id_card_logs', db_index=True)
    card_record = models.ForeignKey(IDCardRecord, on_delete=models.CASCADE, related_name='logs')
    action = models.CharField(max_length=50)  # GENERATED, ISSUED, REISSUED, STATUS_CHANGED, DOWNLOADED
    remarks = models.TextField(blank=True, null=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'id_card_log'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.action} on {self.card_record.card_number} at {self.timestamp}"
