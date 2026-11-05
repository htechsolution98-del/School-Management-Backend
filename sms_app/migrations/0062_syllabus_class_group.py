from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("sms_app", "0061_pagetutorial_show_video_alter_pagetutorial_role")]

    operations = [
        migrations.AlterField(
            model_name="syllabus",
            name="division",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="syllabi", to="sms_app.division"),
        ),
        migrations.AddField(
            model_name="syllabus",
            name="class_group",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="syllabi",
                to="sms_app.schoolclass",
            ),
        ),
        migrations.RunPython(
            lambda apps, schema_editor: [
                apps.get_model("sms_app", "Syllabus").objects.filter(pk=item.pk).update(class_group_id=item.division.SchoolClass_id)
                for item in apps.get_model("sms_app", "Syllabus").objects.select_related("division").iterator()
                if item.division_id and item.division.SchoolClass_id
            ],
            migrations.RunPython.noop,
        ),
    ]
