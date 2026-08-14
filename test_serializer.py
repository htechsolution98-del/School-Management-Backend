import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from sms_app.academic_serializers import SchoolClassSerializer
from sms_app.models import CustomUser, ClassCategory, School, SchoolClass

user = CustomUser.objects.filter(role="CLERK").first()
school = user.school
print(f"School: {school.name}")

category = ClassCategory.objects.first()
print(f"Category: {category.id}")

# Create a class with NO category
sc = SchoolClass.objects.create(school=school, school_class="UncatClass")
print(f"Created UncatClass with ID {sc.id}")

data = {"category": category.id}

class DummyRequest:
    def __init__(self, user):
        self.user = user

context = {"request": DummyRequest(user)}

serializer = SchoolClassSerializer(instance=sc, data=data, partial=True, context=context)
if serializer.is_valid():
    print("Valid!")
    inst = serializer.save()
    print(f"Updated: {inst.school_class} with category {inst.category_id}")
else:
    print("Errors:", serializer.errors)


