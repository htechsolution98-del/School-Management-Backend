from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from sms_app.models import Feature

User = get_user_model()

DEFAULT_FEATURES = [
    "LIBRARIAN",
    "FEES MANAGEMENT",
    "INVENTORY",
    "PRINCIPAL",
    "TRANSPORTATION",
    "TEACHER",
    "CLERK",
    "VICE PRINCIPAL",
    "ASSISTANT CLERK",
]

class Command(BaseCommand):
    help = "Creates default superadmin user and initial features"

    def handle(self, *args, **options):
        # 1. Seed Features
        for feature_name in DEFAULT_FEATURES:
            Feature.objects.get_or_create(name=feature_name)
        self.stdout.write(self.style.SUCCESS("Default Features seeded successfully!"))

        # 2. Seed Superadmin
        username = "superadmin"
        password = "adminpassword123"
        email = "superadmin@gmail.com"
        
        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            user.mobile = "superadmin"
            user.role = "superadmin"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superadmin '{username}' created successfully!"))
        else:
            user.set_password(password)
            user.mobile = "superadmin"
            user.is_superuser = True
            user.is_staff = True
            user.role = "superadmin"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superadmin '{username}' updated successfully!"))
