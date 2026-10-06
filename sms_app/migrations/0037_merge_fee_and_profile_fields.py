from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("sms_app", "0035_feetype_is_rte_applicable_and_more"),
        ("sms_app", "0036_shared_profile_fields"),
    ]

    # Both branches change different models; joining their histories needs no SQL.
    operations = []
