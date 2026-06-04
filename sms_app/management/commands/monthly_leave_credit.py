from django.core.management.base import BaseCommand
from sms_app.models import StaffRemainingLeave


class Command(BaseCommand):
    help = "Apply monthly leave carry forward"

    def handle(self, *args, **kwargs):

        staff_balances = StaffRemainingLeave.objects.select_related(
            "leave_template", "staff"
        )

        updated_count = 0

        for balance in staff_balances:

            # get previous total (same staff + leave type)
            previous = StaffRemainingLeave.objects.filter(
                staff=balance.staff,
                leave_template=balance.leave_template
            ).order_by("-id").first()

            if previous:
                balance.remaining_leaves = (
                    previous.remaining_leaves +
                    balance.leave_template.leave_num
                )
            else:
                balance.remaining_leaves = balance.leave_template.leave_num

            balance.save()
            updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Monthly leave carry forward completed. Updated: {updated_count}"
            )
        )