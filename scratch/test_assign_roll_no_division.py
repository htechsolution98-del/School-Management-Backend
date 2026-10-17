import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from rest_framework import status
from sms_app.models import School, Student, SchoolClass
from sms_app.student_views import AssignRollNumberAPIView

User = get_user_model()

def test_assign_roll_number_division():
    school = School.objects.first()
    # Find or create a clerk user
    user = User.objects.filter(role__iexact="CLERK").first()
    if not user:
        user = User.objects.filter(school=school).first()
    if not user:
        user = User.objects.first()
    
    user.role = "CLERK"
    user.save(update_fields=["role"])

    factory = APIRequestFactory()
    view = AssignRollNumberAPIView.as_view()

    # Test 1: Payload WITHOUT division parameter
    payload1 = {
        "assignments": [
            {"student_id": 1, "roll_no": "1"}
        ]
    }
    request1 = factory.post("/api/assign-roll-numbers/", data=payload1, format="json")
    force_authenticate(request1, user=user)
    response1 = view(request1)
    
    print("Test 1 Status:", response1.status_code)
    print("Test 1 Data:", response1.data)
    assert response1.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400, got {response1.status_code}"
    assert "division" in response1.data, "Expected 'division' in error response"
    assert response1.data["division"] == ["Division is required to assign roll numbers."], f"Unexpected error: {response1.data}"
    print("[PASS] Test 1: Missing division rejected with 400 Bad Request and exact error message.")

    # Test 2: Payload with empty/whitespace or 'ALL' division
    for invalid_div in ["", "   ", "ALL", "all"]:
        payload2 = {
            "division": invalid_div,
            "assignments": [
                {"student_id": 1, "roll_no": "1"}
            ]
        }
        request2 = factory.post("/api/assign-roll-numbers/", data=payload2, format="json")
        force_authenticate(request2, user=user)
        response2 = view(request2)
        assert response2.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400 for '{invalid_div}', got {response2.status_code}"
        assert response2.data["division"] == ["Division is required to assign roll numbers."], f"Unexpected error: {response2.data}"
    print("[PASS] Test 2: Empty/whitespace/ALL division rejected with 400 Bad Request.")

    # Test 3: Payload with valid division parameter
    # Create or find a test student with division 'A'
    cls = SchoolClass.objects.filter(school=school).first()
    if not cls:
        cls = SchoolClass.objects.create(school=school, school_class="Test Class Roll")
    
    st = Student.objects.filter(school=school, gr_no="TEST_ROLL_9999").first()
    if not st:
        st = Student.objects.create(
            school=school,
            gr_no="TEST_ROLL_9999",
            name="Roll Test Student",
            school_class=cls,
            division="A",
        )
    st.division = "A"
    st.save(update_fields=["division"])

    payload3 = {
        "division": "A",
        "assignments": [
            {"student_id": st.id, "roll_no": "99"}
        ]
    }
    request3 = factory.post("/api/assign-roll-numbers/", data=payload3, format="json")
    force_authenticate(request3, user=user)
    response3 = view(request3)
    print("Test 3 Status:", response3.status_code)
    print("Test 3 Data:", response3.data)
    assert response3.status_code == status.HTTP_200_OK, f"Expected 200, got {response3.status_code}"
    st.refresh_from_db()
    assert st.roll_no == "99", f"Expected roll_no '99', got {st.roll_no}"
    print("[PASS] Test 3: Valid division accepted and roll number updated successfully.")

    # Test 4: Student does not belong to specified division
    payload4 = {
        "division": "B",
        "assignments": [
            {"student_id": st.id, "roll_no": "99"}
        ]
    }
    request4 = factory.post("/api/assign-roll-numbers/", data=payload4, format="json")
    force_authenticate(request4, user=user)
    response4 = view(request4)
    assert response4.status_code == status.HTTP_400_BAD_REQUEST, f"Expected 400, got {response4.status_code}"
    assert "division" in response4.data, "Expected 'division' mismatch error"
    print("[PASS] Test 4: Mismatched student division rejected with 400 Bad Request.")

    # Cleanup
    st.delete()
    print("ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_assign_roll_number_division()
