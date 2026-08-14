from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from sms_app.models import School, Feature, SchoolFeature
from sms_app.signals import seed_features_and_school_features, DEFAULT_FEATURES

User = get_user_model()

class Command(BaseCommand):
    help = "Creates default superadmin user, seeds features and initial demo school"

    def handle(self, *args, **options):
        # 1. Create/Update Superadmin User
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

        # 2. Ensure at least one default School exists if database is fresh
        if not School.objects.exists():
            school = School.objects.create(
                login_id=user,
                name="UMA SHIXAN TIRTH",
                code="MG",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Default School '{school.name}' created!"))

        # 3. Seed all features and attach to all schools dynamically
        seed_features_and_school_features()
        self.stdout.write(self.style.SUCCESS("All System Features seeded and attached to Schools!"))
