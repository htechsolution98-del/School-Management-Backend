from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("sms_app", "0072_item_damaged_stock_studentitemissue_status")]

    operations = [
        migrations.AlterField(
            model_name="result",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("VERIFIED", "Verified"),
                    ("APPROVED", "Approved by Principal"),
                    ("SENT_BACK", "Sent Back"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="result",
            name="report_template",
            field=models.CharField(
                choices=[("classic", "Classic School"), ("modern", "Modern Color"), ("compact", "Compact Table")],
                default="classic",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="finalstudentresult",
            name="report_template",
            field=models.CharField(
                choices=[("classic", "Classic School"), ("modern", "Modern Color"), ("compact", "Compact Table")],
                default="classic",
                max_length=20,
            ),
        ),
    ]
