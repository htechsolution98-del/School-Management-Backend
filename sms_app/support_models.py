import uuid
from django.db import models
from django.conf import settings
from .models import School


def generate_ticket_number():
    """Generates a clean ticket identifier like TCK-20261010-XXXX"""
    from django.utils import timezone
    date_str = timezone.now().strftime("%Y%m%d")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"TCK-{date_str}-{unique_suffix}"


class SupportTicket(models.Model):
    PRIORITY_CHOICES = [
        ("LOW", "Low"),
        ("MEDIUM", "Medium"),
        ("HIGH", "High"),
        ("URGENT", "Urgent"),
    ]

    CATEGORY_CHOICES = [
        ("GENERAL", "General Inquiry"),
        ("TECHNICAL", "Technical Issue / Bug"),
        ("FEES", "Fees & Finance"),
        ("INVENTORY", "Inventory & Assets"),
        ("ACADEMIC", "Academic & Exams"),
        ("ACCOUNT", "Account & Access"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending (Waiting for Super Admin)"),
        ("IN_PROGRESS", "In Progress (Chat Open)"),
        ("CLOSED", "Closed"),
    ]

    ticket_number = models.CharField(
        max_length=64, unique=True, default=generate_ticket_number, db_index=True
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, null=True, blank=True, related_name="support_tickets"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_support_tickets",
        db_index=True,
    )
    requester_role = models.CharField(max_length=64, default="STAFF")
    requester_name = models.CharField(max_length=255, blank=True, null=True)

    subject = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, default="GENERAL")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="MEDIUM")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING", db_index=True)

    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_support_tickets",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_support_tickets",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closing_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "support_ticket"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["created_by", "status"]),
            models.Index(fields=["school", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.ticket_number} - {self.subject} ({self.get_status_display()})"


class TicketMessage(models.Model):
    MESSAGE_TYPES = [
        ("TEXT", "Text Message"),
        ("MEDIA", "Media Attachment"),
        ("SYSTEM", "System Notification"),
    ]

    ticket = models.ForeignKey(
        SupportTicket, on_delete=models.CASCADE, related_name="messages", db_index=True
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ticket_messages",
    )
    sender_role = models.CharField(max_length=64, default="USER")
    sender_name = models.CharField(max_length=255, blank=True, null=True)
    message_type = models.CharField(max_length=16, choices=MESSAGE_TYPES, default="TEXT")

    text_content = models.TextField(blank=True, null=True)
    media_file = models.FileField(
        upload_to="support_attachments/%Y/%m/%d/", blank=True, null=True
    )
    media_name = models.CharField(max_length=255, blank=True, null=True)
    media_size_bytes = models.PositiveIntegerField(default=0)
    media_content_type = models.CharField(max_length=128, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "support_ticket_message"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]

    def __str__(self):
        return f"Msg #{self.id} on {self.ticket.ticket_number} by {self.sender_name or 'System'}"
