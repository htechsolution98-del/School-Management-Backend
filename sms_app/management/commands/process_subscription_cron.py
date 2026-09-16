from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from sms_app.models import SchoolSubscription
from sms_app.subscription_services import AuditLogService, SubscriptionBillingService


class Command(BaseCommand):
    help = "Processes subscription state transitions, expiry warnings, and grace periods."

    def handle(self, *args, **options):
        today = timezone.now().date()
        self.stdout.write(f"Running subscription background check for {today}...")

        subscriptions = SchoolSubscription.objects.select_related("school").all()
        updated_count = 0

        for sub in subscriptions:
            old_status = sub.status

            if sub.status in ["TRIAL", "ACTIVE", "EXPIRING"]:
                # Check for expiring soon (within 7 days)
                if today <= sub.due_date <= (today + timedelta(days=7)) and sub.status == "ACTIVE":
                    sub.status = "EXPIRING"
                    sub.save(update_fields=["status"])
                    updated_count += 1
                    AuditLogService.log(
                        action="SUBSCRIPTION_EXPIRING_SOON",
                        school=sub.school,
                        new_values={"status": "EXPIRING", "due_date": str(sub.due_date)},
                        notes=f"Subscription expires in {(sub.due_date - today).days} days.",
                    )

                # Check if past due date
                elif sub.due_date < today:
                    effective_due = sub.due_date + timedelta(days=sub.grace_period_days)
                    if today <= effective_due:
                        if sub.status != "GRACE_PERIOD":
                            sub.status = "GRACE_PERIOD"
                            sub.save(update_fields=["status"])
                            updated_count += 1
                            AuditLogService.log(
                                action="GRACE_PERIOD_STARTED",
                                school=sub.school,
                                old_values={"status": old_status},
                                new_values={"status": "GRACE_PERIOD"},
                                notes=f"School entered grace period until {effective_due}.",
                            )
                    else:
                        new_status = "TRIAL_EXPIRED" if sub.plan_type == "TRIAL" else "EXPIRED"
                        if sub.auto_lock_on_due:
                            new_status = "SUSPENDED"
                            if sub.school.is_active:
                                sub.school.is_active = False
                                sub.school.save(update_fields=["is_active"])

                        sub.status = new_status
                        sub.save(update_fields=["status"])
                        updated_count += 1
                        AuditLogService.log(
                            action="SUBSCRIPTION_EXPIRED_OR_SUSPENDED",
                            school=sub.school,
                            old_values={"status": old_status},
                            new_values={"status": new_status},
                            notes=f"Subscription expired past grace period. Status set to {new_status}.",
                        )

        self.stdout.write(self.style.SUCCESS(f"Subscription background check complete. Updated {updated_count} subscriptions."))
