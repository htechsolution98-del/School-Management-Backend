import datetime
from decimal import Decimal
from django.utils import timezone
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status

from sms_app.models import (
    School,
    Staff,
    Attendance,
    AttendanceSetting,
    AttendanceRegularization,
    FeeType,
)

User = get_user_model()


class SecurityPhase1Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. School setup
        self.superadmin = User.objects.create_superuser(
            username="superadmin_test", password="password123", email="superadmin@test.com"
        )
        self.school = School.objects.create(name="Security Test Academy", login_id=self.superadmin)

        # 2. Staff & User profiles
        # Admin / Clerk
        self.clerk_user = User.objects.create_user(
            username="clerk_user", password="password123", role="CLERK", school=self.school
        )
        self.clerk_staff = Staff.objects.create(
            user=self.clerk_user, school=self.school, name="Test Clerk", category="CLERK", email="clerk@test.com"
        )

        # Teacher
        self.teacher_user = User.objects.create_user(
            username="teacher_user", password="password123", role="TEACHER", school=self.school
        )
        self.teacher_staff = Staff.objects.create(
            user=self.teacher_user, school=self.school, name="Teacher Alice", category="TEACHER", email="teacher@test.com"
        )

        # Librarian
        self.librarian_user = User.objects.create_user(
            username="librarian_user", password="password123", role="LIBRARIAN", school=self.school
        )
        self.librarian_staff = Staff.objects.create(
            user=self.librarian_user, school=self.school, name="Librarian Bob", category="LIBRARIAN", email="librarian@test.com"
        )

        # Inventory Manager
        self.inventory_user = User.objects.create_user(
            username="inventory_user", password="password123", role="INVENTORY", school=self.school
        )
        self.inventory_staff = Staff.objects.create(
            user=self.inventory_user, school=self.school, name="Inventory Charlie", category="INVENTORY", email="inventory@test.com"
        )

        # Fees Management
        self.fee_user = User.objects.create_user(
            username="fee_user", password="password123", role="FEES MANAGEMENT", school=self.school
        )
        self.fee_staff = Staff.objects.create(
            user=self.fee_user, school=self.school, name="Fee David", category="FEES MANAGEMENT", email="fee@test.com"
        )

        # Another teacher in the same school
        self.teacher2_user = User.objects.create_user(
            username="teacher2_user", password="password123", role="TEACHER", school=self.school
        )
        self.teacher2_staff = Staff.objects.create(
            user=self.teacher2_user, school=self.school, name="Teacher Eve", category="TEACHER", email="teacher2@test.com"
        )

        # Attendance setting
        self.setting = AttendanceSetting.objects.create(
            school=self.school,
            name="General Shift",
            check_in_time=datetime.time(9, 0),
            check_out_time=datetime.time(17, 0),
            grace_period_mins=15,
            half_day_threshold_mins=120,
            geo_required=False,
            is_active=True,
        )

    # =========================================================================
    # 1. Attendance Regularization Data Leakage & Permission Tests
    # =========================================================================

    def test_normal_staff_can_only_see_own_regularization_requests(self):
        # Teacher Alice creates a request
        reg_alice = AttendanceRegularization.objects.create(
            staff=self.teacher_staff,
            attendance_date=datetime.date(2026, 10, 1),
            requested_check_in=datetime.time(9, 15),
            reason="Bus breakdown",
            status="Pending",
        )
        # Teacher Eve creates a request
        reg_eve = AttendanceRegularization.objects.create(
            staff=self.teacher2_staff,
            attendance_date=datetime.date(2026, 10, 2),
            requested_check_in=datetime.time(9, 20),
            reason="Medical checkup",
            status="Pending",
        )

        # Librarian logs in
        self.client.force_authenticate(user=self.librarian_user)
        res = self.client.get("/api/attendance-regularizations/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        ids = [r["id"] for r in (res.data if isinstance(res.data, list) else res.data.get("results", []))]
        self.assertNotIn(reg_alice.id, ids)
        self.assertNotIn(reg_eve.id, ids)

        # Inventory user logs in
        self.client.force_authenticate(user=self.inventory_user)
        res = self.client.get("/api/attendance-regularizations/")
        ids = [r["id"] for r in (res.data if isinstance(res.data, list) else res.data.get("results", []))]
        self.assertNotIn(reg_alice.id, ids)
        self.assertNotIn(reg_eve.id, ids)

        # Fees Management user logs in
        self.client.force_authenticate(user=self.fee_user)
        res = self.client.get("/api/attendance-regularizations/")
        ids = [r["id"] for r in (res.data if isinstance(res.data, list) else res.data.get("results", []))]
        self.assertNotIn(reg_alice.id, ids)
        self.assertNotIn(reg_eve.id, ids)

        # Librarian tries to retrieve Alice's record directly
        res = self.client.get(f"/api/attendance-regularizations/{reg_alice.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Clerk / Admin can see all requests
        self.client.force_authenticate(user=self.clerk_user)
        res = self.client.get("/api/attendance-regularizations/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        clerk_ids = [r["id"] for r in (res.data if isinstance(res.data, list) else res.data.get("results", []))]
        self.assertIn(reg_alice.id, clerk_ids)
        self.assertIn(reg_eve.id, clerk_ids)

    def test_regularization_create_ignores_client_staff_id_for_normal_users(self):
        # Librarian tries to submit a regularization specifying Teacher Alice's staff ID
        self.client.force_authenticate(user=self.librarian_user)
        payload = {
            "staff": self.teacher_staff.id,  # Trying to spoof Alice
            "attendance_date": "2026-10-05",
            "requested_check_in": "09:10:00",
            "requested_check_out": "17:05:00",
            "reason": "Traffic jam",
        }
        res = self.client.post("/api/attendance-regularizations/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_id = res.data["id"]

        created_reg = AttendanceRegularization.objects.get(id=created_id)
        # Must be bound to Librarian's staff profile, NOT Alice
        self.assertEqual(created_reg.staff.id, self.librarian_staff.id)
        self.assertNotEqual(created_reg.staff.id, self.teacher_staff.id)

    def test_regularization_update_and_delete_permissions(self):
        # Teacher Alice creates a request
        reg_alice = AttendanceRegularization.objects.create(
            staff=self.teacher_staff,
            attendance_date=datetime.date(2026, 10, 1),
            requested_check_in=datetime.time(9, 15),
            reason="Initial reason",
            status="Pending",
        )

        # Another teacher tries to update Alice's request
        self.client.force_authenticate(user=self.teacher2_user)
        res = self.client.patch(
            f"/api/attendance-regularizations/{reg_alice.id}/",
            data={"reason": "Hacked reason"},
            format="json",
        )
        self.assertIn(res.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN])

        # Alice updates her own pending request
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.patch(
            f"/api/attendance-regularizations/{reg_alice.id}/",
            data={"reason": "Updated reason"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        reg_alice.refresh_from_db()
        self.assertEqual(reg_alice.reason, "Updated reason")

    def test_regularization_approval_restricted_to_hr_management(self):
        reg = AttendanceRegularization.objects.create(
            staff=self.teacher_staff,
            attendance_date=datetime.date(2026, 10, 3),
            requested_check_in=datetime.time(9, 0),
            requested_check_out=datetime.time(17, 0),
            reason="Forgot punch",
            status="Pending",
        )

        # Fees Management tries to approve
        self.client.force_authenticate(user=self.fee_user)
        res = self.client.post(f"/api/attendance-regularizations/{reg.id}/approve/", data={"note": "Approved by fees"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Librarian tries to approve
        self.client.force_authenticate(user=self.librarian_user)
        res = self.client.post(f"/api/attendance-regularizations/{reg.id}/approve/", data={"note": "Approved by lib"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Clerk approves
        self.client.force_authenticate(user=self.clerk_user)
        res = self.client.post(f"/api/attendance-regularizations/{reg.id}/approve/", data={"note": "Approved by clerk"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        reg.refresh_from_db()
        self.assertEqual(reg.status, "Approved")
        self.assertEqual(reg.approved_by, self.clerk_user)

    # =========================================================================
    # 2. Attendance View Restrictions (HTTP 405 on PUT/PATCH/DELETE) & Corrections
    # =========================================================================

    def test_attendance_put_patch_delete_returns_http_405(self):
        att = Attendance.objects.create(
            school=self.school,
            staff=self.teacher_staff,
            name=self.teacher_staff.name,
            category="TEACHER",
            attendance_date=datetime.date(2026, 10, 4),
            is_present=True,
        )

        self.client.force_authenticate(user=self.teacher_user)

        # PUT must return 405 Method Not Allowed
        res_put = self.client.put(f"/api/attendance/{att.id}/", data={"is_present": False}, format="json")
        self.assertEqual(res_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PATCH must return 405 Method Not Allowed
        res_patch = self.client.patch(f"/api/attendance/{att.id}/", data={"is_present": False}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # DELETE must return 405 Method Not Allowed
        res_del = self.client.delete(f"/api/attendance/{att.id}/")
        self.assertEqual(res_del.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_attendance_correction_process_and_audit_trail(self):
        att = Attendance.objects.create(
            school=self.school,
            staff=self.teacher_staff,
            name=self.teacher_staff.name,
            category="TEACHER",
            attendance_date=datetime.date(2026, 10, 4),
            is_present=True,
            is_late=True,
            source="Punch",
        )

        # Non-management user (Teacher) tries to correct attendance -> 403 Forbidden
        self.client.force_authenticate(user=self.teacher_user)
        res = self.client.post(
            f"/api/attendance/{att.id}/correct/",
            data={"is_late": False, "reason": "Self correction"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Fees Management tries to correct attendance -> 403 Forbidden
        self.client.force_authenticate(user=self.fee_user)
        res = self.client.post(
            f"/api/attendance/{att.id}/correct/",
            data={"is_late": False, "reason": "Fee correction"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Authorized Clerk corrects attendance
        self.client.force_authenticate(user=self.clerk_user)
        res = self.client.post(
            f"/api/attendance/{att.id}/correct/",
            data={
                "check_in": "09:00:00",
                "check_out": "17:00:00",
                "is_late": False,
                "is_present": True,
                "reason": "Biometric device malfunction verified by principal",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        att.refresh_from_db()
        self.assertFalse(att.is_late)
        self.assertEqual(att.source, "Admin Correction")
        self.assertEqual(att.working_hours, Decimal("8.00"))
        self.assertTrue(len(att.correction_log) >= 1)

        last_entry = att.correction_log[-1]
        self.assertEqual(last_entry["action"], "Correction")
        self.assertEqual(last_entry["by"], self.clerk_user.id)
        self.assertEqual(last_entry["reason"], "Biometric device malfunction verified by principal")
        self.assertTrue(last_entry["previous_state"]["is_late"])
        self.assertFalse(last_entry["new_state"]["is_late"])

    # =========================================================================
    # 3. Fees Management Role Separation
    # =========================================================================

    def test_fees_management_cannot_change_school_wide_attendance_settings(self):
        self.client.force_authenticate(user=self.fee_user)

        # Try to modify attendance setting
        res = self.client.patch(
            f"/api/attendance-settings/{self.setting.id}/",
            data={"grace_period_mins": 30},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Try to create new attendance setting
        res = self.client.post(
            "/api/attendance-settings/",
            data={
                "name": "Fee Shift",
                "check_in_time": "08:00:00",
                "check_out_time": "16:00:00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_fees_management_can_access_fee_features(self):
        # Create a fee type for testing
        fee_type = FeeType.objects.create(school=self.school, name="Tuition Fee")

        self.client.force_authenticate(user=self.fee_user)
        res = self.client.get("/api/feetype/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
