from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from sms_app.models import FeeType


class Command(BaseCommand):
    help = "Assigns 'view_feetype' permission to Inventory and Clerk groups."

    def handle(self, *args, **options):
        # 1. Fetch content type and permission for FeeType
        try:
            content_type = ContentType.objects.get_for_model(FeeType)
            view_feetype_perm = Permission.objects.get(
                codename="view_feetype",
                content_type=content_type,
            )
        except ContentType.DoesNotExist:
            self.stdout.write(self.style.ERROR("ContentType for FeeType model does not exist."))
            return
        except Permission.DoesNotExist:
            self.stdout.write(self.style.ERROR("Permission 'view_feetype' does not exist."))
            return

        target_names = [
            "Inventory Manager",
            "INVENTORY",
            "inventory",
            "inventory manager",
            "Clerk",
            "CLERK",
            "clerk",
            "Assistant Clerk",
            "ASSISTANT CLERK",
            "assistant clerk",
            "FEES MANAGEMENT",
            "fees management",
        ]

        # Collect groups case-insensitively or create if absent
        assigned_count = 0
        already_had_count = 0
        processed_group_ids = set()

        for name in target_names:
            group = Group.objects.filter(name__iexact=name).first()
            if not group:
                try:
                    group = Group.objects.create(name=name)
                except Exception:
                    # In case of database-level case collisions, fetch again
                    group = Group.objects.filter(name__iexact=name).first()

            if not group or group.id in processed_group_ids:
                continue

            processed_group_ids.add(group.id)

            if not group.permissions.filter(id=view_feetype_perm.id).exists():
                group.permissions.add(view_feetype_perm)
                assigned_count += 1
                self.stdout.write(self.style.SUCCESS(f"  + [Assigned] 'view_feetype' to Group: '{group.name}' (ID: {group.id})"))
            else:
                already_had_count += 1
                self.stdout.write(self.style.NOTICE(f"  = [Already Present] 'view_feetype' in Group: '{group.name}' (ID: {group.id})"))

        # Also find any other groups with inventory or clerk in name
        extra_groups = Group.objects.filter(
            Q(name__icontains="inventory") | Q(name__icontains="clerk")
        ).exclude(id__in=processed_group_ids)

        for group in extra_groups:
            processed_group_ids.add(group.id)
            if not group.permissions.filter(id=view_feetype_perm.id).exists():
                group.permissions.add(view_feetype_perm)
                assigned_count += 1
                self.stdout.write(self.style.SUCCESS(f"  + [Assigned] 'view_feetype' to Group: '{group.name}' (ID: {group.id})"))
            else:
                already_had_count += 1
                self.stdout.write(self.style.NOTICE(f"  = [Already Present] 'view_feetype' in Group: '{group.name}' (ID: {group.id})"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSuccessfully configured permissions across {len(processed_group_ids)} groups ({assigned_count} newly assigned, {already_had_count} already active)."
            )
        )
