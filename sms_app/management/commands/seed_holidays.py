from django.core.management.base import BaseCommand
from sms_app.holiday_defaults import seed_default_holidays_for_all_schools

class Command(BaseCommand):
    help = "Seed standard Indian school public holidays for all schools"

    def handle(self, *args, **options):
        count = seed_default_holidays_for_all_schools()
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded {count} default school public holidays."))
