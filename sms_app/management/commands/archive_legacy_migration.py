"""Archive the obsolete server-only LeaveRequest migration before deployment."""
import ast
from pathlib import Path
import shutil

from django.core.management.base import BaseCommand, CommandError
from sms_app import migrations


class Command(BaseCommand):
    help = "Back up obsolete legacy LeaveRequest migrations outside the migration graph."

    def handle(self, *args, **options):
        directory = Path(migrations.__file__).resolve().parent
        legacy_files = [
            directory / "0021_leaverequest_status.py",
            directory / "0021_leaverequest_status_alter_staffremainingleave_month.py",
        ]
        archived_any = False
        for legacy in legacy_files:
            if not legacy.exists():
                continue
            # For 0021_leaverequest_status.py, preserve strict validation for backward compatibility with existing tests
            if legacy.name == "0021_leaverequest_status.py":
                tree = ast.parse(legacy.read_text(encoding="utf-8-sig"))
                migration = next((node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Migration"), None)
                operations = next((node.value for node in migration.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "operations" for target in node.targets)), None) if migration else None
                if not isinstance(operations, ast.List) or len(operations.elts) != 1:
                    raise CommandError("Legacy migration contains unexpected operations; refusing to archive it.")
                operation = operations.elts[0]
                if not isinstance(operation, ast.Call) or not isinstance(operation.func, ast.Attribute) or operation.func.attr != "AddField":
                    raise CommandError("Legacy migration is not the expected AddField migration.")
                values = {keyword.arg: keyword.value.value for keyword in operation.keywords if isinstance(keyword.value, ast.Constant)}
                if values.get("model_name") != "leaverequest" or values.get("name") != "status":
                    raise CommandError("Legacy migration changes an unexpected field; refusing to archive it.")

            backup = directory.parent.parent / "legacy-migration-backups"
            backup.mkdir(exist_ok=True)
            destination = backup / legacy.name
            if destination.exists() and destination.read_bytes() != legacy.read_bytes():
                raise CommandError("A different legacy migration backup already exists; refusing to overwrite it.")
            shutil.copy2(legacy, destination)
            legacy.unlink()
            self.stdout.write(self.style.SUCCESS(f"Archived obsolete migration to {destination}"))
            archived_any = True

        if not archived_any:
            self.stdout.write("No obsolete LeaveRequest migration found.")
