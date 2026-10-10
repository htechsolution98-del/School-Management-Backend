import os
import django
import datetime
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from sms_app.models import (
    School, Staff, Attendance, AttendanceSetting, AttendanceLocation,
    BiometricVerificationProof
)
from sms_app.utils import generate_biometric_proof, validate_and_consume_biometric_proof
from sms_app.academic_serializers import AttendanceSerializer

User = get_user_model()

def test_biometric_flow():
    print("=== STARTING BIOMETRIC & OVERNIGHT TESTS ===")
    
    # 1. Setup Test School & Staff
    school = School.objects.first()
    assert school is not None, "At least one school must exist in DB"
    
    loc, _ = AttendanceLocation.objects.get_or_create(
        school=school,
        defaults={
            "latitude": 23.0225,
            "longitude": 72.5714,
            "radius": 500,
        }
    )
    
    user1, _ = User.objects.get_or_create(username="biometric_staff_1", defaults={"email": "bio1@test.com"})
    staff1, _ = Staff.objects.get_or_create(
        user=user1,
        defaults={"name": "Bio Staff One", "school": school, "category": "TEACHING"}
    )
    
    user2, _ = User.objects.get_or_create(username="biometric_staff_2", defaults={"email": "bio2@test.com"})
    staff2, _ = Staff.objects.get_or_create(
        user=user2,
        defaults={"name": "Bio Staff Two", "school": school, "category": "TEACHING"}
    )

    policy = AttendanceSetting.objects.filter(school=school).first()
    if not policy:
        policy = AttendanceSetting.objects.create(
            school=school,
            is_active=True,
            geo_required=False,
            biometric_required=True,
        )
    policy.biometric_required = True
    policy.geo_required = False
    policy.save()

    print("[1] Test generate_biometric_proof...")
    proof = generate_biometric_proof(staff=staff1, school=school, confidence=Decimal("95.50"))
    assert proof.token is not None
    assert proof.is_used is False
    assert proof.expires_at > timezone.now()
    print("  -> Proof token generated:", proof.token[:12], "...")

    print("[2] Test validate_and_consume_biometric_proof (single-use / replay protection)...")
    ok, msg = validate_and_consume_biometric_proof(proof.token, staff=staff1, school=school)
    assert ok, f"Failed: {msg}"
    proof.refresh_from_db()
    assert proof.is_used
    print("  -> First consumption SUCCESS")

    # Second consumption should FAIL (Replay prevention)
    ok, msg = validate_and_consume_biometric_proof(proof.token, staff=staff1, school=school)
    assert not ok
    assert "already been used" in msg
    print("  -> Replay attack rejected SUCCESS:", msg)

    print("[3] Test cross-staff token rejection...")
    proof_staff2 = generate_biometric_proof(staff=staff2, school=school)
    ok, msg = validate_and_consume_biometric_proof(proof_staff2.token, staff=staff1, school=school)
    assert ok is False
    assert "does not belong to this staff" in msg
    print("  -> Cross-staff proof rejected SUCCESS:", msg)

    print("[4] Test expired token rejection...")
    expired_proof = generate_biometric_proof(staff=staff1, school=school, expires_in_minutes=-5)
    ok, msg = validate_and_consume_biometric_proof(expired_proof.token, staff=staff1, school=school)
    assert ok is False
    assert "expired" in msg
    print("  -> Expired proof rejected SUCCESS:", msg)

    print("[5] Test AttendanceSerializer with valid verification_token...")
    # Clean previous attendances for staff1
    Attendance.objects.filter(staff=staff1).delete()
    
    proof_punch = generate_biometric_proof(staff=staff1, school=school)
    
    class FakeRequest:
        def __init__(self, user):
            self.user = user

    serializer = AttendanceSerializer(
        data={"verification_token": proof_punch.token},
        context={"request": FakeRequest(user1)}
    )
    assert serializer.is_valid(), serializer.errors
    att = serializer.save()
    assert att.check_in is not None
    assert att.check_out is None
    proof_punch.refresh_from_db()
    assert proof_punch.is_used is True
    print("  -> Check-in with biometric token SUCCESS, att ID:", att.id)

    print("[6] Test Overnight Shift Check-out...")
    # Suppose check-in was at 10 PM yesterday
    yesterday = timezone.localdate() - datetime.timedelta(days=1)
    yesterday_checkin = timezone.now() - datetime.timedelta(hours=8)
    att.attendance_date = yesterday
    att.check_in = yesterday_checkin
    att.save()

    # Now staff punches again to check out (next morning)
    proof_out = generate_biometric_proof(staff=staff1, school=school)
    serializer2 = AttendanceSerializer(
        data={"verification_token": proof_out.token},
        context={"request": FakeRequest(user1)}
    )
    assert serializer2.is_valid(), serializer2.errors
    att_out = serializer2.save()
    assert att_out.id == att.id, "Should update same overnight attendance session!"
    assert att_out.check_out is not None
    assert att_out.working_hours > Decimal("7.0") # approximately 8 hours
    print(f"  -> Overnight shift check-out SUCCESS! Working hours: {att_out.working_hours} hrs")

    print("[7] Test Duplicate Check-out prevention...")
    proof_dup = generate_biometric_proof(staff=staff1, school=school)
    serializer_dup = AttendanceSerializer(
        data={"verification_token": proof_dup.token},
        context={"request": FakeRequest(user1)}
    )
    # Today attendance is already checked out, so punch should reject
    # Wait, staff1's previous attendance had attendance_date=yesterday. Let's make an attendance today that is checked out:
    att_today = Attendance.objects.create(
        school=school,
        staff=staff1,
        attendance_date=timezone.localdate(),
        check_in=timezone.now() - datetime.timedelta(hours=2),
        check_out=timezone.now() - datetime.timedelta(hours=1),
        is_present=True,
    )
    serializer_dup = AttendanceSerializer(
        data={"verification_token": proof_dup.token},
        context={"request": FakeRequest(user1)}
    )
    assert not serializer_dup.is_valid()
    print("  -> Duplicate check-out prevented SUCCESS:", serializer_dup.errors)

    print("[8] Test Biometric Required when token missing in production mode vs bypass...")
    # Switch bypass OFF
    settings.ALLOW_BIOMETRIC_BYPASS = False
    old_debug = settings.DEBUG
    settings.DEBUG = False
    try:
        # Create a fresh staff3
        user3, _ = User.objects.get_or_create(username="biometric_staff_3")
        staff3, _ = Staff.objects.get_or_create(user=user3, defaults={"name": "Bio Staff Three", "school": school})
        serializer_no_token = AttendanceSerializer(
            data={},
            context={"request": FakeRequest(user3)}
        )
        assert not serializer_no_token.is_valid()
        assert "verification_token" in serializer_no_token.errors
        print("  -> Missing token rejected in strict mode SUCCESS:", serializer_no_token.errors["verification_token"])
    finally:
        settings.ALLOW_BIOMETRIC_BYPASS = True
        settings.DEBUG = old_debug

    print("\nALL 8 BIOMETRIC & OVERNIGHT SECURITY TESTS PASSED PERFECTLY!\n")

if __name__ == "__main__":
    test_biometric_flow()
