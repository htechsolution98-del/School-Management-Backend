from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from sms_app.models import School, Feature, SchoolFeature
from sms_app.signals import seed_features_and_school_features

User = get_user_model()

class Command(BaseCommand):
    help = "Creates default superadmin user, seeds features, demo school, and demo staff accounts"

    def handle(self, *args, **options):
        # 1. Create/Update Superadmin User
        username = "superadmin"
        password = "Super123"
        email = "superadmin@example.com"
        
        user = User.objects.filter(username=username).first() or User.objects.filter(email=email).first()
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
            user.username = username
            user.email = email
            user.set_password(password)
            user.mobile = "superadmin"
            user.is_superuser = True
            user.is_staff = True
            user.role = "superadmin"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superadmin '{username}' updated successfully!"))

        # 2. Ensure at least one default School exists if database is fresh
        school = School.objects.first()
        if not school:
            school = School.objects.create(
                login_id=user,
                name="UMA SHIXAN TIRTH",
                code="MG",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Default School '{school.name}' created!"))

        if not user.school:
            user.school = school
            user.save()

        # 3. Demo Staff Users to create/reset with password "123456"
        demo_users = [
            {
                "username": "Harikesh4277",
                "email": "harikesh@gmail.com",
                "mobile": "7984649969",
                "role": "CLERK",
                "group": "CLERK",
                "first_name": "Harikesh",
                "last_name": "Clerk",
            },
            {
                "username": "Mansi4614",
                "email": "mansi@gmail.com",
                "mobile": "7046062012",
                "role": "FEES MANAGEMENT",
                "group": "FEES MANAGEMENT",
                "first_name": "Mansi",
                "last_name": "FeeManager",
            },
            {
                "username": "Nikunj1170",
                "email": "nikunj@gmail.com",
                "mobile": "1234567890",
                "role": "PRINCIPAL",
                "group": "PRINCIPAL",
                "first_name": "Nikunj",
                "last_name": "Principal",
            },
            {
                "username": "Sujal2821",
                "email": "sujal@gmail.com",
                "mobile": "9999999999",
                "role": "TEACHER",
                "group": "TEACHER",
                "first_name": "Sujal",
                "last_name": "Teacher",
            },
            {
                "username": "MG7981",
                "email": "mahilmaurya2005@gmail.com",
                "mobile": "9876543210",
                "role": "admin(trustee)",
                "group": "admin(trustee)",
                "first_name": "Mahil",
                "last_name": "Trustee",
            },
        ]

        default_password = "123456"

        for udata in demo_users:
            group_obj, _ = Group.objects.get_or_create(name=udata["group"])
            u = (
                User.objects.filter(email__iexact=udata["email"]).first()
                or User.objects.filter(username__iexact=udata["username"]).first()
            )
            if not u:
                u = User.objects.create(
                    username=udata["username"],
                    email=udata["email"],
                    mobile=udata["mobile"],
                    role=udata["role"],
                    school=school,
                    first_name=udata["first_name"],
                    last_name=udata["last_name"],
                    is_active=True,
                )
                u.set_password(default_password)
                u.save()
                u.groups.add(group_obj)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created demo user: {udata['email']} / {udata['username']}"
                    )
                )
            else:
                u.set_password(default_password)
                u.role = udata["role"]
                u.school = school
                u.is_active = True
                u.save()
                u.groups.add(group_obj)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated password for demo user: {udata['email']} / {udata['username']}"
                    )
                )

        # 4. Seed all features and attach to all schools dynamically
        seed_features_and_school_features()
        self.stdout.write(
            self.style.SUCCESS("All System Features seeded and attached to Schools!")
        )
