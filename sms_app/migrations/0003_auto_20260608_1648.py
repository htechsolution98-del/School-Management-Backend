from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sms_app', '0002_auto_20260608_1628'),
    ]

    operations = [
        migrations.AddField(
            model_name='leavetemplate',
            name='leave_type_fk',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='sms_app.leavetype',
            ),
        ),

        migrations.AddField(
            model_name='leaverequest',
            name='leave_type_fk',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='sms_app.leavetype',
            ),
        ),
    ]