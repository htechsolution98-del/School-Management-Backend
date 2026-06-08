from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('sms_app', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='CertificateType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, null=True, blank=True)),
                ('school', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='sms_app.school')),
            ],
            options={
                'db_table': 'certificate_type',
            },
        ),

        migrations.CreateModel(
            name='CertificateRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(
                    max_length=20,
                    choices=[
                        ('PENDING', 'Pending'),
                        ('APPROVED', 'Approved'),
                        ('REJECTED', 'Rejected'),
                    ],
                    default='PENDING'
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('certificate_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='sms_app.certificatetype')),
                ('school', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='sms_app.school')),
            ],
            options={
                'db_table': 'certificate_request',
            },
        ),

        migrations.CreateModel(
            name='LeaveType',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, null=True, blank=True)),
                ('school', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='sms_app.school')),
            ],
            options={
                'db_table': 'leave_type',
            },
        ),
    ]