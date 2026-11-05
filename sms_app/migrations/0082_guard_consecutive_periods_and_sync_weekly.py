from django.db import migrations


def guard_consecutive_and_sync_weekly(apps, schema_editor):
    Staff = apps.get_model("sms_app", "Staff")

    for s in Staff.objects.all():
        needs_save = False

        mon = s.max_periods_mon if s.max_periods_mon is not None else 5
        tue = s.max_periods_tue if s.max_periods_tue is not None else 5
        wed = s.max_periods_wed if s.max_periods_wed is not None else 5
        thu = s.max_periods_thu if s.max_periods_thu is not None else 5
        fri = s.max_periods_fri if s.max_periods_fri is not None else 5
        sat = s.max_periods_sat if s.max_periods_sat is not None else 3

        # Cap Saturday operational limit to 3 if half-day
        if sat > 3:
            sat = 3
            s.max_periods_sat = 3
            needs_save = True

        correct_weekly = mon + tue + wed + thu + fri + sat

        if s.max_weekly_periods != correct_weekly:
            s.max_weekly_periods = correct_weekly
            needs_save = True

        if s.max_consecutive_periods is None or s.max_consecutive_periods < 2:
            s.max_consecutive_periods = 2 if correct_weekly <= 15 and correct_weekly > 0 else 3
            needs_save = True

        if needs_save:
            s.save()


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0081_leavetype_leave_unit"),
    ]

    operations = [
        migrations.RunPython(guard_consecutive_and_sync_weekly, reverse_code=migrations.RunPython.noop),
    ]
