from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0076_alter_schoolprofile_board_affiliation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="staff",
            name="department",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="sms_app.department",
            ),
        ),
    ]

