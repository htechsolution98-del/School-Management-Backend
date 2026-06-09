from django.core.management.base import BaseCommand
from datetime import datetime

from sms_app.models import (
    Staff,
    LeaveTemplate,
    StaffRemainingLeave
)


class Command(BaseCommand):
    help = "Carry forward leave balances"

    def handle(self, *args, **kwargs):

        today = datetime.today()

        current_month = today.month
        current_year = today.year

        if current_month == 12:
            month = 1
            year = current_year + 1
        else:
            month = current_month + 1
            year = current_year

        for template in LeaveTemplate.objects.all():

            staff = template.staff

            existing = StaffRemainingLeave.objects.filter(
                staff=staff,
                leave_template=template,
                month=month,
                year=year
            ).first()

            if existing:
                continue

            if month == 1:
                previous_month = 12
                previous_year = year - 1
            else:
                previous_month = month - 1
                previous_year = year

            previous_record = StaffRemainingLeave.objects.filter(
                staff=staff,
                leave_template=template,
                month=previous_month,
                year=previous_year
            ).first()

            carry_forward = 0

            if previous_record:
                carry_forward = previous_record.remaining_leaves

            StaffRemainingLeave.objects.create(
                school=template.school,
                staff=staff,
                leave_template=template,
                month=month,
                year=year,
                total_leaves=template.leave_num,
                carry_forward_leaves=carry_forward,
                remaining_leaves=template.leave_num + carry_forward
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Leave carry-forward completed."
            )
        )