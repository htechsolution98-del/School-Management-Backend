from django.db import models


class Announcement(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    announcement_for = models.CharField(max_length=50, default="ALL")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_announcement"

    def __str__(self):
        return self.title


class StudentNotification(models.Model):
    student = models.ForeignKey("student_admission.Student", on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_student_notification"


class BoardMeeting(models.Model):
    title = models.CharField(max_length=255)
    meeting_date = models.DateTimeField()
    agenda = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "notification_board_meeting"
