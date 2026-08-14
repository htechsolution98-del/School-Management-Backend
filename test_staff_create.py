import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from sms_app.models import Staff, Department, School, Feature
from django.contrib.auth import get_user_model
User = get_user_model()
from rest_framework.test import APIClient

client = APIClient()
# Find a clerk user
user = User.objects.filter(groups__name="CLERK").first()
if not user:
    # try trustee
    user = User.objects.filter(groups__name="admin(trustee)").first()

client.force_authenticate(user=user)

dept = Department.objects.filter(school=user.school).first()
if not dept:
    dept = Department.objects.create(name="Test Dept", school=user.school)

cat = Feature.objects.filter(name="CLERK").first()

data = {
    "name": "Test Staff",
    "email": "teststaff@example.com",
    "mobile": "1234567890",
    "category": cat.id,
    "department": dept.id,
    "address": "Test",
    "date_of_birth": "2026-01-01",
    "salary": "1000",
    "is_active": True
}

print(f"Payload: {data}")

response = client.post('/api/StaffView/', data, format='json')
print("Status:", response.status_code)
print("Response:", response.data)

staff = Staff.objects.order_by('-id').first()
print("Staff created with department:", staff.department)
