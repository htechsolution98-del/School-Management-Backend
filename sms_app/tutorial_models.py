from django.db import models
from django.conf import settings

ROLE_CHOICES = (
    ('CLERK', 'Clerk'),
    ('PRINCIPAL', 'Principal'),
    ('TEACHER', 'Teacher'),
    ('TRUSTEE', 'Trustee'),
    ('FEES', 'Fees Management'),
    ('INVENTORY', 'Inventory'),
    ('GLOBAL', 'Global / All Roles'),
)

class PageTutorial(models.Model):
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, db_index=True)
    route_path = models.CharField(max_length=255, db_index=True)
    title = models.CharField(max_length=255)
    summary = models.TextField(blank=True, default='')
    steps = models.JSONField(
        default=list,
        blank=True,
        help_text="List of steps: [{'step': 1, 'title': '...', 'description': '...', 'dummy_example': '...'}]"
    )
    dummy_data = models.JSONField(
        default=list,
        blank=True,
        help_text="List of dummy data/fields: [{'field': '...', 'sample_value': '...', 'instructions': '...'}]"
    )
    video_url = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Optional YouTube / Vimeo / Drive URL"
    )
    tips = models.JSONField(
        default=list,
        blank=True,
        help_text="List of helpful tips: ['Tip 1', 'Tip 2']"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_tutorials'
    )

    class Meta:
        db_table = "page_tutorial"
        unique_together = ('role', 'route_path')
        ordering = ['role', 'route_path']

    def __str__(self):
        return f"[{self.role}] {self.title} ({self.route_path})"
