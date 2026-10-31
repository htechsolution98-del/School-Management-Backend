from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sms_app", "0073_result_report_template")]

    operations = [
        migrations.AlterField(
            model_name="result",
            name="report_template",
            field=models.CharField(
                choices=[
                    ("classic", "Classic School"),
                    ("modern", "Modern Color"),
                    ("compact", "Compact Table"),
                    ("watermark", "School Watermark"),
                ],
                default="classic",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="finalstudentresult",
            name="report_template",
            field=models.CharField(
                choices=[
                    ("classic", "Classic School"),
                    ("modern", "Modern Color"),
                    ("compact", "Compact Table"),
                    ("watermark", "School Watermark"),
                ],
                default="classic",
                max_length=20,
            ),
        ),
    ]
