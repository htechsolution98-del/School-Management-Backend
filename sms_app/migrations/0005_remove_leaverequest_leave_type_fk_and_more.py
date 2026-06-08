from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0004_auto_20260608_1655"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.RemoveField(
                    model_name="leaverequest",
                    name="leave_type_fk",
                ),
                migrations.RemoveField(
                    model_name="leavetemplate",
                    name="leave_type_fk",
                ),
            ],
        ),
    ]