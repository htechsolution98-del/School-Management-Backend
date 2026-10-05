import importlib
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.db import connections, models
from django.db.backends.sqlite3.base import DatabaseWrapper

from sms_app.management.commands.archive_legacy_migration import Command


LEGACY = '''from django.db import migrations, models
class Migration(migrations.Migration):
    dependencies = [('sms_app', '0020_alter_schoolclass_school_class_classcategory_and_more')]
    operations = [migrations.AddField(model_name='leaverequest', name='status', field=models.CharField(max_length=20))]
'''


class ArchiveLegacyMigrationTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'sms_app' / 'migrations'
        self.directory.mkdir(parents=True)
        self.legacy = self.directory / '0021_leaverequest_status.py'
        self.backup = self.root / 'legacy-migration-backups' / self.legacy.name
        self.command = Command(stdout=StringIO())
        patcher = patch('sms_app.management.commands.archive_legacy_migration.migrations.__file__', str(self.directory / '__init__.py'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_archives_expected_file_and_preserves_content(self):
        self.legacy.write_text(LEGACY)
        self.command.handle()
        self.assertFalse(self.legacy.exists())
        self.assertEqual(self.backup.read_text(), LEGACY)
        self.command.handle()  # Repeated deployments are safe.

    def test_missing_file_is_a_noop(self):
        self.command.handle()
        self.assertFalse(self.backup.exists())

    def test_unexpected_field_is_preserved(self):
        self.legacy.write_text(LEGACY.replace("name='status'", "name='other'"))
        with self.assertRaises(CommandError):
            self.command.handle()
        self.assertTrue(self.legacy.exists())

    def test_extra_operations_are_preserved(self):
        self.legacy.write_text(LEGACY.replace('operations = [', 'operations = [migrations.RunPython(print), '))
        with self.assertRaises(CommandError):
            self.command.handle()
        self.assertTrue(self.legacy.exists())

    def test_conflicting_backup_is_preserved(self):
        self.legacy.write_text(LEGACY)
        self.backup.parent.mkdir()
        self.backup.write_text('earlier backup')
        with self.assertRaises(CommandError):
            self.command.handle()
        self.assertTrue(self.legacy.exists())
        self.assertEqual(self.backup.read_text(), 'earlier backup')


class StatusColumnCompatibilityTests(SimpleTestCase):
    def test_real_database_preserves_legacy_status_data(self):
        class LeaveRequestProbe(models.Model):
            class Meta:
                app_label = 'sms_app'
                managed = False
                db_table = 'legacy_status_probe'

        database = DatabaseWrapper({
            'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:',
            'OPTIONS': {}, 'TIME_ZONE': None, 'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False, 'AUTOCOMMIT': True,
        }, alias='migration_probe')
        connections['migration_probe'] = database
        self.addCleanup(connections.__delitem__, 'migration_probe')
        self.addCleanup(database.close)
        migration = importlib.import_module('sms_app.migrations.0021_leaverequest_status_student_roll_no')
        apps = MagicMock()
        apps.get_model.return_value = LeaveRequestProbe
        with database.schema_editor(atomic=False) as editor:
            editor.create_model(LeaveRequestProbe)
            migration.add_status_if_missing(apps, editor)
        with database.cursor() as cursor:
            cursor.execute("INSERT INTO legacy_status_probe (status) VALUES ('APPROVED')")
        with database.schema_editor(atomic=False) as editor:
            migration.add_status_if_missing(apps, editor)
        with database.cursor() as cursor:
            cursor.execute('SELECT status FROM legacy_status_probe')
            self.assertEqual(cursor.fetchall(), [('APPROVED',)])

    def test_existing_status_column_is_not_added_again(self):
        migration = importlib.import_module('sms_app.migrations.0021_leaverequest_status_student_roll_no')
        editor = MagicMock()
        editor.connection.introspection.get_table_description.return_value = [SimpleNamespace(name='status')]
        migration.add_status_if_missing(MagicMock(), editor)
        editor.add_field.assert_not_called()

    def test_missing_status_column_is_added(self):
        migration = importlib.import_module('sms_app.migrations.0021_leaverequest_status_student_roll_no')
        editor = MagicMock()
        editor.connection.introspection.get_table_description.return_value = [SimpleNamespace(name='id')]
        apps = MagicMock()
        migration.add_status_if_missing(apps, editor)
        model, field = editor.add_field.call_args.args
        self.assertEqual(model, apps.get_model.return_value)
        self.assertEqual(field.column, 'status')
        self.assertEqual(field.default, 'PENDING')
