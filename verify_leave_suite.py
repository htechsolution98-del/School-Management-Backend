import os
import sys
import uuid
import django
from datetime import date, timedelta
from decimal import Decimal

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sms.settings")
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied

from sms_app.models import (
    School,
    Staff,
    LeaveCycle,
    LeaveTemplate,
    LeaveType,
    LeaveRequest,
    LeavePerDay,
    LeaveBalance,
    LeaveTransaction,
    Attendance,
    Holiday,
)
from sms_app.services.leave_service import (
    LeaveValidationService,
    LeaveWorkflowService,
    LeaveAttendanceSyncService,
    LeaveAllocationService,
    LeaveCycleClosingService,
)

User = get_user_model()


def run_all_checks():
    print("=" * 60, flush=True)
    print("STARTING LEAVE MANAGEMENT TEST SUITE", flush=True)
    print("=" * 60, flush=True)

    uid = uuid.uuid4().hex[:6]

    with transaction.atomic():
        # Setup Schools
        user_a = User.objects.create_user(username=f"adm_a_{uid}", email=f"adm_a_{uid}@test.com", password="pass")
        school_a = School.objects.create(name=f"School Alpha {uid}", code=f"A_{uid}", slug=f"school-alpha-{uid}", login_id=user_a)

        user_b = User.objects.create_user(username=f"adm_b_{uid}", email=f"adm_b_{uid}@test.com", password="pass")
        school_b = School.objects.create(name=f"School Beta {uid}", code=f"B_{uid}", slug=f"school-beta-{uid}", login_id=user_b)

        # Setup Principal and Teacher
        principal_user = User.objects.create_user(username=f"prn_{uid}", email=f"prn_{uid}@test.com", role="PRINCIPAL", school=school_a)
        principal_staff = Staff.objects.create(name="Principal Sharma", user=principal_user, school=school_a, category="PRINCIPAL", is_active=True)

        teacher_user = User.objects.create_user(username=f"tch_{uid}", email=f"tch_{uid}@test.com", role="TEACHER", school=school_a)
        teacher_staff = Staff.objects.create(name="Teacher Patel", user=teacher_user, school=school_a, category="TEACHER", is_active=True, joining_date=date(2026, 1, 1))

        # Setup Cycle & Template & Types
        cycle_2026 = LeaveCycle.objects.create(school=school_a, name=f"2026-2027-{uid}", start_date=date(2026, 4, 1), end_date=date(2027, 3, 31), is_active=True)
        template = LeaveTemplate.objects.create(school=school_a, name="Teaching Policy", time_line="ANNUAL", is_active=True)
        teacher_staff.leave_template = template
        teacher_staff.save()

        cl_type = LeaveType.objects.create(
            leave_template=template,
            name="Casual Leave",
            leave_type="CASUAL_LEAVE",
            code="CL",
            is_paid=True,
            allocation_count=Decimal("12.0"),
            carry_forward=True,
            max_carry_forward=5,
            half_day_allowed=True,
            include_weekends=False,
            include_holidays=False,
            allow_negative_balance=False,
            allow_future_leave=True,
            allow_backdated_leave=True,
            max_backdated_days=7,
            prorata_on_joining="PRO_RATA",
        )

        cl_balance = LeaveBalance.objects.create(
            staff=teacher_staff,
            leave_type=cl_type,
            leave_cycle=cycle_2026,
            opening_balance=Decimal("0.0"),
            allocated=Decimal("12.0"),
            carry_forward=Decimal("0.0"),
            used=Decimal("0.0"),
            pending=Decimal("0.0"),
        )

        print("[Setup] Test entities initialized cleanly.", flush=True)

        # Test 1: Submission & Balance Reservation
        req1 = LeaveWorkflowService.submit_leave_request(
            staff=teacher_staff, school=school_a, leave_type=cl_type,
            start_date=date(2026, 11, 2), end_date=date(2026, 11, 4), reason="Event", requested_by=teacher_user
        )
        cl_balance.refresh_from_db()
        assert req1.status == "PENDING"
        assert req1.total_days == Decimal("3.0")
        assert cl_balance.pending == Decimal("3.0")
        assert cl_balance.available == Decimal("9.0")
        print("[PASS]: Test 1 - Balance Reservation on Leave Submission", flush=True)

        # Test 2: Withdrawal releases reservation
        LeaveWorkflowService.withdraw_leave_request(req1, teacher_user)
        req1.refresh_from_db()
        cl_balance.refresh_from_db()
        assert req1.status == "CANCELLED"
        assert cl_balance.pending == Decimal("0.0")
        assert cl_balance.available == Decimal("12.0")
        print("[PASS]: Test 2 - Withdrawal Releases Reservation Cleanly", flush=True)

        # Test 3: Self-Approval prevention & Principal approval
        req2 = LeaveWorkflowService.submit_leave_request(
            staff=teacher_staff, school=school_a, leave_type=cl_type,
            start_date=date(2026, 11, 16), end_date=date(2026, 11, 17), reason="Seminar", requested_by=teacher_user
        )
        self_denied = False
        try:
            LeaveWorkflowService.approve_leave_request(req2, teacher_user, school_a)
        except PermissionDenied:
            self_denied = True
        assert self_denied, "Self-approval must be rejected!"

        LeaveWorkflowService.approve_leave_request(req2, principal_user, school_a)
        req2.refresh_from_db()
        cl_balance.refresh_from_db()
        assert req2.status == "APPROVED"
        assert cl_balance.used == Decimal("2.0")
        assert cl_balance.available == Decimal("10.0")

        att_records = Attendance.objects.filter(staff=teacher_staff, attendance_date__in=[date(2026, 11, 16), date(2026, 11, 17)], source="Leave")
        assert att_records.count() == 2
        print("[PASS]: Test 3 - Self-Approval Blocked & Attendance Synced on Approval", flush=True)

        # Test 4: Insufficient Balance Rejection
        insufficient_failed = False
        try:
            LeaveWorkflowService.submit_leave_request(
                staff=teacher_staff, school=school_a, leave_type=cl_type,
                start_date=date(2026, 12, 1), end_date=date(2026, 12, 25), reason="Vacation", requested_by=teacher_user
            )
        except ValidationError:
            insufficient_failed = True
        assert insufficient_failed, "Over-limit request must be rejected!"
        print("[PASS]: Test 4 - Insufficient Balance Rejected with Validation Error", flush=True)

        # Test 5: Half-day collision and coexistence
        h1 = LeaveWorkflowService.submit_leave_request(
            staff=teacher_staff, school=school_a, leave_type=cl_type,
            start_date=date(2026, 11, 25), end_date=date(2026, 11, 25),
            reason="Morning", is_half_day=True, half_day_session="FIRST_HALF", requested_by=teacher_user
        )
        assert h1.total_days == Decimal("0.5")

        h_dup_failed = False
        try:
            LeaveWorkflowService.submit_leave_request(
                staff=teacher_staff, school=school_a, leave_type=cl_type,
                start_date=date(2026, 11, 25), end_date=date(2026, 11, 25),
                reason="Morning dup", is_half_day=True, half_day_session="FIRST_HALF", requested_by=teacher_user
            )
        except ValidationError:
            h_dup_failed = True
        assert h_dup_failed, "Duplicate half-day session must be rejected"

        h2 = LeaveWorkflowService.submit_leave_request(
            staff=teacher_staff, school=school_a, leave_type=cl_type,
            start_date=date(2026, 11, 25), end_date=date(2026, 11, 25),
            reason="Afternoon", is_half_day=True, half_day_session="SECOND_HALF", requested_by=teacher_user
        )
        assert h2.total_days == Decimal("0.5")
        print("[PASS]: Test 5 - Half-Day Collision Blocked & Complementary Session Allowed", flush=True)

        # Test 6: Holiday and Weekend Exclusions
        eff_days = LeaveValidationService.get_effective_leave_days(school_a, cl_type, date(2026, 11, 21), date(2026, 11, 24))
        eff_dates = [d[0] for d in eff_days]
        assert date(2026, 11, 22) not in eff_dates, "Sunday weekend must be excluded"
        assert date(2026, 11, 24) not in eff_dates, "Holiday (Guru Nanak Jayanti) must be excluded"
        assert date(2026, 11, 21) in eff_dates, "Saturday must be included"
        assert date(2026, 11, 23) in eff_dates, "Monday must be included"
        print("[PASS]: Test 6 - Holiday and Weekend Deductions Excluded per Policy", flush=True)

        # Test 7: Cancellation Workflow and Balance Refund
        LeaveWorkflowService.request_cancellation(req2, teacher_user, "Event postponed")
        req2.refresh_from_db()
        assert req2.cancellation_status == "REQUESTED"

        LeaveWorkflowService.approve_cancellation(req2, principal_user, school_a)
        req2.refresh_from_db()
        cl_balance.refresh_from_db()
        assert req2.status == "CANCELLED"
        assert req2.cancellation_status == "APPROVED"
        assert cl_balance.used == Decimal("0.0")
        assert not Attendance.objects.filter(staff=teacher_staff, attendance_date=date(2026, 11, 16)).exists()
        print("[PASS]: Test 7 - Cancellation Approved, Balance Refunded & Attendance Reverted", flush=True)

        # Test 8: Pro-Rata Joining Date Allocation
        mid_staff = Staff.objects.create(name="Mid Staff", school=school_a, category="TEACHER", joining_date=date(2026, 10, 1), leave_template=template, is_active=True)
        allocs = LeaveAllocationService.allocate_leaves_for_staff(mid_staff, cycle_2026)
        mid_bal = LeaveBalance.objects.get(staff=mid_staff, leave_type=cl_type, leave_cycle=cycle_2026)
        assert mid_bal.allocated == Decimal("6.0")

        allocs2 = LeaveAllocationService.allocate_leaves_for_staff(mid_staff, cycle_2026)
        assert len(allocs2) == 0
        print("[PASS]: Test 8 - Pro-Rata Allocation (6.0 days) and Idempotency Verified", flush=True)

        # Test 9: Cycle Closing and Carry-Forward Limits
        cl_balance.used = Decimal("2.0")
        cl_balance.save()
        cycle_2027 = LeaveCycle.objects.create(school=school_a, name=f"2027-2028-{uid}", start_date=date(2027, 4, 1), end_date=date(2028, 3, 31), is_active=False)

        LeaveCycleClosingService.close_cycle(cycle_2026, cycle_2027, user=principal_user)
        cycle_2026.refresh_from_db()
        cycle_2027.refresh_from_db()
        assert cycle_2026.is_closed
        assert cycle_2027.is_active

        next_bal = LeaveBalance.objects.get(staff=teacher_staff, leave_type=cl_type, leave_cycle=cycle_2027)
        assert next_bal.carry_forward == Decimal("5.0")

        exp_tx = LeaveTransaction.objects.filter(staff=teacher_staff, transaction_type="EXPIRY").first()
        assert exp_tx and exp_tx.amount == Decimal("5.0")
        print("[PASS]: Test 9 - Cycle Closing with Carry-Forward Limit (5.0) and Expiry (5.0)", flush=True)

        # Rollback all test changes
        transaction.set_rollback(True)
        print("[Teardown] Transaction rolled back safely. Database is completely untouched.", flush=True)

    print("=" * 60, flush=True)
    print("ALL LEAVE MANAGEMENT TESTS COMPLETED SUCCESSFULLY WITH 100% PASS RATE", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    run_all_checks()
