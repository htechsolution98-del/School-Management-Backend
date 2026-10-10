import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from django.utils import timezone
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient
from rest_framework import status
from decimal import Decimal

from sms_app.models import (
    School, Staff, Attendance, AttendanceSetting, AttendanceRegularization,
    BiometricVerificationProof
)
from sms_app.utils import generate_biometric_proof

User = get_user_model()

def run_role_security_tests():
    print("=== TESTING ALL 8 ROLES SECURITY & ACCESS BOUNDARIES ===")
    
    school_a = School.objects.first()
    assert school_a is not None, "School A must exist"

    # Ensure a second school exists for cross-school isolation testing
    school_b = School.objects.exclude(id=school_a.id).first()
    if not school_b:
        school_b = School.objects.create(name="School B Isolated Test", login_id=school_a.login_id)

    client = APIClient()

    # Helper to setup a role user & staff
    def setup_user_and_staff(role_name, username, school=school_a, category=None):
        user, _ = User.objects.get_or_create(username=username, defaults={"role": role_name})
        user.role = role_name
        user.save()
        staff, _ = Staff.objects.get_or_create(
            user=user,
            defaults={"name": f"Test {role_name}", "school": school, "category": category or role_name}
        )
        staff.school = school
        staff.category = category or role_name
        staff.save()
        return user, staff

    # 1. Setup All 8 Roles
    u_principal, s_principal = setup_user_and_staff("PRINCIPAL", "test_principal_user")
    u_vp, s_vp = setup_user_and_staff("VICE PRINCIPAL", "test_vp_user")
    u_clerk, s_clerk = setup_user_and_staff("CLERK", "test_clerk_user")
    u_asst_clerk, s_asst_clerk = setup_user_and_staff("ASSISTANT CLERK", "test_asst_clerk_user")
    u_teacher, s_teacher = setup_user_and_staff("TEACHER", "test_teacher_user")
    u_fees, s_fees = setup_user_and_staff("FEES MANAGEMENT", "test_fees_user")
    u_inventory, s_inventory = setup_user_and_staff("INVENTORY", "test_inv_user")
    u_librarian, s_librarian = setup_user_and_staff("LIBRARIAN", "test_lib_user")

    # School B staff
    u_school_b, s_school_b = setup_user_and_staff("TEACHER", "test_school_b_teacher", school=school_b)

    # -------------------------------------------------------------
    # TEST 1: Principal & Vice Principal Access & Audit Trail
    # -------------------------------------------------------------
    print("\n[1] Testing Principal & Vice Principal Access...")
    client.force_authenticate(user=u_principal)
    
    # Create an attendance record for teacher
    att_teacher, _ = Attendance.objects.get_or_create(
        school=school_a,
        staff=s_teacher,
        attendance_date=timezone.localdate(),
        defaults={"name": s_teacher.name, "category": s_teacher.category, "is_present": True}
    )

    # Principal can correct with reason & audit log
    resp = client.post(f"/api/attendance/{att_teacher.id}/correct/", {"reason": "Principal updated checkin time", "check_in": "09:00:00"})
    assert resp.status_code == status.HTTP_200_OK, f"Principal correction failed: {resp.data}"
    att_teacher.refresh_from_db()
    assert len(att_teacher.correction_log) > 0
    assert att_teacher.correction_log[-1]["corrected_by"] == u_principal.username
    print("  -> Principal Attendance Correction with Audit Log SUCCESS")

    # Principal CANNOT access School B records
    att_b = Attendance.objects.create(
        school=school_b,
        staff=s_school_b,
        attendance_date=timezone.localdate(),
        name=s_school_b.name,
        category="TEACHING",
        is_present=True
    )
    resp_b = client.post(f"/api/attendance/{att_b.id}/correct/", {"reason": "Cross school attack", "check_in": "09:00:00"})
    assert resp_b.status_code == status.HTTP_404_NOT_FOUND, f"Cross-school isolation failed: {resp_b.status_code}"
    print("  -> Principal cross-school access strictly denied (HTTP 404) SUCCESS")

    # -------------------------------------------------------------
    # TEST 2: Self-Approval Prevention on Regularization
    # -------------------------------------------------------------
    print("\n[2] Testing Self-Approval Prevention...")
    # Principal creates a regularization for themselves
    reg_principal = AttendanceRegularization.objects.create(
        staff=s_principal,
        attendance_date=timezone.localdate(),
        reason="Principal personal regularization",
        status="Pending"
    )
    # Principal attempts to approve own request
    resp = client.post(f"/api/attendance-regularizations/{reg_principal.id}/approve/", {})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, f"Self-approval should be forbidden: {resp.status_code}"
    assert "You cannot approve your own regularization request" in str(resp.data)
    print("  -> Self-approval strictly forbidden (HTTP 403) SUCCESS")

    # Vice Principal can approve Principal's request
    client.force_authenticate(user=u_vp)
    resp_vp = client.post(f"/api/attendance-regularizations/{reg_principal.id}/approve/", {})
    assert resp_vp.status_code == status.HTTP_200_OK, f"VP approval failed: {resp_vp.data}"
    reg_principal.refresh_from_db()
    assert reg_principal.status == "Approved"
    print("  -> Independent approver (VP) approved Principal request SUCCESS")

    # -------------------------------------------------------------
    # TEST 3: Clerk & Assistant Clerk Restricted Access
    # -------------------------------------------------------------
    print("\n[3] Testing Clerk & Assistant Clerk Restrictions...")
    # Standard Clerk attempts to approve a regularization
    reg_teacher = AttendanceRegularization.objects.create(
        staff=s_teacher,
        attendance_date=timezone.localdate(),
        reason="Teacher forgot to punch out",
        status="Pending"
    )
    client.force_authenticate(user=u_clerk)
    resp_clerk_app = client.post(f"/api/attendance-regularizations/{reg_teacher.id}/approve/", {})
    assert resp_clerk_app.status_code == status.HTTP_403_FORBIDDEN, f"Clerk should not have approval rights: {resp_clerk_app.status_code}"
    print("  -> Standard Clerk approval denied (HTTP 403) SUCCESS")

    # Standard Clerk attempts to correct attendance
    resp_clerk_corr = client.post(f"/api/attendance/{att_teacher.id}/correct/", {"reason": "Clerk fix", "check_in": "09:00:00"})
    assert resp_clerk_corr.status_code == status.HTTP_403_FORBIDDEN, f"Clerk should not have correction rights: {resp_clerk_corr.status_code}"
    print("  -> Standard Clerk attendance correction denied (HTTP 403) SUCCESS")

    # Assistant Clerk attempts to approve or correct
    client.force_authenticate(user=u_asst_clerk)
    resp_asst_app = client.post(f"/api/attendance-regularizations/{reg_teacher.id}/approve/", {})
    assert resp_asst_app.status_code == status.HTTP_403_FORBIDDEN
    resp_asst_corr = client.post(f"/api/attendance/{att_teacher.id}/correct/", {"reason": "Asst fix", "check_in": "09:00:00"})
    assert resp_asst_corr.status_code == status.HTTP_403_FORBIDDEN
    print("  -> Assistant Clerk approval and correction denied (HTTP 403) SUCCESS")

    # But Clerk CAN view attendance records (Attendance Operations)
    client.force_authenticate(user=u_clerk)
    resp_view = client.get("/api/attendance/")
    assert resp_view.status_code == status.HTTP_200_OK
    print("  -> Clerk can view school staff attendance operations SUCCESS")

    # -------------------------------------------------------------
    # TEST 4: Teacher, Fees Management, Inventory, Librarian Data Scoping
    # -------------------------------------------------------------
    print("\n[4] Testing Self-Attendance Scoping for Teacher, Fees, Inventory, Librarian...")
    roles_to_test = [
        ("Teacher", u_teacher, s_teacher),
        ("Fees Management", u_fees, s_fees),
        ("Inventory Manager", u_inventory, s_inventory),
        ("Librarian", u_librarian, s_librarian),
    ]

    for r_label, u_obj, s_obj in roles_to_test:
        client.force_authenticate(user=u_obj)
        
        # 1. Cannot see other staff attendance
        resp_att = client.get("/api/attendance/")
        assert resp_att.status_code == status.HTTP_200_OK
        results = resp_att.data.get("results", resp_att.data) if isinstance(resp_att.data, dict) else resp_att.data
        for item in results:
            assert item["staff"] == s_obj.id, f"{r_label} leaked another staff's attendance!"
        
        # 2. Cannot see other staff regularization
        resp_reg = client.get("/api/attendance-regularizations/")
        assert resp_reg.status_code == status.HTTP_200_OK
        reg_results = resp_reg.data.get("results", resp_reg.data) if isinstance(resp_reg.data, dict) else resp_reg.data
        for r_item in reg_results:
            assert r_item["staff"] == s_obj.id, f"{r_label} leaked another staff's regularization!"
        
        # 3. Cannot approve or correct
        resp_app = client.post(f"/api/attendance-regularizations/{reg_teacher.id}/approve/", {})
        assert resp_app.status_code == status.HTTP_403_FORBIDDEN
        resp_corr = client.post(f"/api/attendance/{att_teacher.id}/correct/", {"reason": "hack"})
        assert resp_corr.status_code == status.HTTP_403_FORBIDDEN
        
        print(f"  -> {r_label} strictly restricted to self-attendance only SUCCESS")

    # -------------------------------------------------------------
    # TEST 5: Mock-Face Bypass Active in Development Mode
    # -------------------------------------------------------------
    print("\n[5] Testing Development Mock-Face Bypass Mode...")
    assert settings.ALLOW_BIOMETRIC_BYPASS is True
    client.force_authenticate(user=u_teacher)
    resp_checkin = client.post("/api/attendance/", {"latitude": 23.0225, "longitude": 72.5714})
    assert resp_checkin.status_code == status.HTTP_201_CREATED, f"Dev bypass check-in failed: {resp_checkin.data}"
    print("  -> Development Mock-Face Bypass Check-in SUCCESS")

    print("\n========================================================")
    print("ALL 8 ROLES SECURITY & ACCESS BOUNDARIES TESTS PASSED!")
    print("========================================================\n")

if __name__ == "__main__":
    run_role_security_tests()
