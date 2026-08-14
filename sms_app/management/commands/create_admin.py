from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = "Creates default superadmin user"

    def handle(self, *args, **options):
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
            user.role = "superadmin"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superadmin '{username}' created successfully!"))
        else:
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.role = "superadmin"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superadmin '{username}' updated successfully!"))
