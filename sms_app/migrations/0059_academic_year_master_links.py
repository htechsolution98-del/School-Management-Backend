# Generated manually for linking academic year text fields to AcademicYear master.

import django.db.models.deletion
from django.db import migrations, models


def link_existing_academic_years(apps, schema_editor):
    AcademicYear = apps.get_model("sms_app", "AcademicYear")
    Student = apps.get_model("sms_app", "Student")
    Timetable = apps.get_model("sms_app", "Timetable")

    def get_or_create_year(school_id, name):
        if not school_id or not name:
            return None

        year_name = str(name).strip()
        if not year_name:
            return None

        academic_year = AcademicYear.objects.filter(
            school_id=school_id,
            name=year_name,
        ).first()

        if not academic_year:
            academic_year = AcademicYear.objects.create(
                school_id=school_id,
                name=year_name,
            )

        return academic_year

    for student in Student.objects.exclude(academic_year__isnull=True).exclude(
        academic_year=""
    ):
        academic_year = get_or_create_year(student.school_id, student.academic_year)
        if academic_year:
            student.academic_year_fk_id = academic_year.id
            student.save(update_fields=["academic_year_fk"])

    for timetable in Timetable.objects.exclude(academic_year__isnull=True).exclude(
        academic_year=""
    ):
        academic_year = get_or_create_year(timetable.school_id, timetable.academic_year)
        if academic_year:
            timetable.academic_year_fk_id = academic_year.id
            timetable.save(update_fields=["academic_year_fk"])


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("sms_app", "0058_parent_tempuser"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="timetable",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="student",
            name="academic_year_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="sms_app.academicyear",
            ),
        ),
        migrations.AddField(
            model_name="timetable",
            name="academic_year_fk",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="sms_app.academicyear",
            ),
        ),
        migrations.RunPython(link_existing_academic_years, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="student",
            name="academic_year",
        ),
        migrations.RemoveField(
            model_name="timetable",
            name="academic_year",
        ),
        migrations.RenameField(
            model_name="student",
            old_name="academic_year_fk",
            new_name="academic_year",
        ),
        migrations.RenameField(
            model_name="timetable",
            old_name="academic_year_fk",
            new_name="academic_year",
        ),
        migrations.AlterUniqueTogether(
            name="timetable",
            unique_together={("school", "class_div", "academic_year")},
        ),
    ]
