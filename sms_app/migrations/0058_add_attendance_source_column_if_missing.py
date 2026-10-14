from django.db import migrations


def add_attendance_source_column_if_missing(apps, schema_editor):
    """Repair databases where migration 0046 recorded ``source`` only in state."""
    Attendance = apps.get_model("sms_app", "Attendance")
    table_name = Attendance._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        table_names = connection.introspection.table_names(cursor)
        if table_name not in table_names:
            raise RuntimeError(
                f"Expected attendance table {table_name!r} before adding its source column."
            )

        columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, table_name)
        }

    if "source" not in columns:
        schema_editor.add_field(Attendance, Attendance._meta.get_field("source"))


class Migration(migrations.Migration):
    dependencies = [
        ("sms_app", "0057_merge_book_fines_and_certificate_library"),
    ]

    operations = [
        migrations.RunPython(
            add_attendance_source_column_if_missing,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
