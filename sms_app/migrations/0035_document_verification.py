from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("sms_app", "0034_student_verification_abc_udise"),
        ("sms_app", "0033_alter_inventorybundle_unique_together_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="admissiondocument", name="is_verified", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="admissiondocument", name="verified_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="admissiondocument", name="verified_by", field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="+")),
        migrations.AddField(model_name="studentdocument", name="is_verified", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="studentdocument", name="verified_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="studentdocument", name="verified_by", field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="+")),
        migrations.AddField(model_name="rtedocument", name="verified_at", field=models.DateTimeField(null=True, blank=True)),
        migrations.AddField(model_name="rtedocument", name="verified_by", field=models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.SET_NULL, null=True, blank=True, related_name="+")),
    ]
