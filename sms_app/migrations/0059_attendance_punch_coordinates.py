from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sms_app", "0058_add_attendance_source_column_if_missing")]

    operations = [
        migrations.AddField(model_name="attendance", name="check_in_latitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="attendance", name="check_in_longitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="attendance", name="check_out_latitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
        migrations.AddField(model_name="attendance", name="check_out_longitude", field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True)),
    ]
