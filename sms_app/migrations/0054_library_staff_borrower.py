from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('sms_app', '0053_merge_20261010_1859')]
    operations = [
        migrations.AlterField(model_name='bookissued', name='student', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='sms_app.student')),
        migrations.AddField(model_name='bookissued', name='staff', field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='library_loans', to='sms_app.staff')),
        migrations.AddConstraint(model_name='bookissued', constraint=models.CheckConstraint(condition=models.Q(student__isnull=False, staff__isnull=True) | models.Q(student__isnull=True, staff__isnull=False), name='library_loan_exactly_one_borrower')),
    ]
