from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('sms_app', '0003_auto_20260608_1648'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE leave_template
                DROP COLUMN leave_type;

                ALTER TABLE leave_request
                DROP COLUMN leave_type;

                ALTER TABLE leave_template
                RENAME COLUMN leave_type_fk_id TO leave_type_id;

                ALTER TABLE leave_request
                RENAME COLUMN leave_type_fk_id TO leave_type_id;
            """,
            reverse_sql="""
                ALTER TABLE leave_template
                RENAME COLUMN leave_type_id TO leave_type_fk_id;

                ALTER TABLE leave_request
                RENAME COLUMN leave_type_id TO leave_type_fk_id;

                ALTER TABLE leave_template
                ADD COLUMN leave_type varchar(100);

                ALTER TABLE leave_request
                ADD COLUMN leave_type varchar(100);
            """
        ),
    ]