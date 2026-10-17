import os
import django
import datetime

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from django.utils import timezone
from sms_app.models import School, Staff, Feature, Department
from django.contrib.auth import get_user_model
from sms_app.staff_serializers import StaffSerializer

User = get_user_model()

def test_reactivation():
    school = School.objects.first()
    user, _ = User.objects.get_or_create(username="test_react_staff", defaults={"email": "react_staff@test.com", "role": "TEACHER"})
    dept = Department.objects.filter(school=school).first()
    
    staff, _ = Staff.objects.get_or_create(
        school=school,
        user=user,
        defaults={
            "name": "Test Reactivate Staff",
            "email": "react_staff@test.com",
            "mobile": "9876543210",
            "category": "TEACHER",
            "department": dept,
            "salary": "30000.00",
            "is_active": True,
        }
    )

    today = timezone.localdate()
    yesterday = today - datetime.timedelta(days=1)
    tomorrow = today + datetime.timedelta(days=10)

    # Test 1: Setting past exit_date deactivates
    serializer = StaffSerializer(instance=staff, data={"exit_date": yesterday.isoformat()}, partial=True)
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.is_active is False, f"Expected is_active False, got {updated.is_active}"
    assert updated.exit_date == yesterday, f"Expected {yesterday}, got {updated.exit_date}"
    print("[PASS] Test 1: Setting past exit date deactivates staff (is_active = False)")

    # Test 2: Clearing exit_date (None) automatically reactivates staff (is_active = True)
    serializer = StaffSerializer(instance=updated, data={"exit_date": None}, partial=True)
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.is_active is True, f"Expected is_active True, got {updated.is_active}"
    assert updated.exit_date is None, f"Expected None, got {updated.exit_date}"
    print("[PASS] Test 2: Clearing exit date (None) auto-reactivates staff (is_active = True)")

    # Test 3: Setting past exit date again, then setting future exit date reactivates
    serializer = StaffSerializer(instance=updated, data={"exit_date": yesterday.isoformat()}, partial=True)
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.is_active is False
    
    serializer = StaffSerializer(instance=updated, data={"exit_date": tomorrow.isoformat()}, partial=True)
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.is_active is True, f"Expected is_active True, got {updated.is_active}"
    print("[PASS] Test 3: Changing past exit date to future exit date auto-reactivates staff (is_active = True)")

    # Test 4: Explicit manual override: exit_date is None, but is_active is explicitly False
    serializer = StaffSerializer(instance=updated, data={"exit_date": None, "is_active": False}, partial=True)
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.is_active is False, f"Expected is_active False when explicitly requested, got {updated.is_active}"
    print("[PASS] Test 4: Manual override with exit_date=None and is_active=False preserves is_active=False")

    # Clean up test user & staff
    staff.delete()
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_reactivation()
