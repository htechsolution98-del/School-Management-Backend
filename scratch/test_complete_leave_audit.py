import os
import sys
sys.path.insert(0, os.path.abspath("."))
import django
from datetime import date, timedelta
from decimal import Decimal

os.environ['DJANGO_SETTINGS_MODULE'] = 'sms.settings'
django.setup()

from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from sms_app.models import (
    School, Staff, LeaveType, LeaveCycle, LeaveBalance, LeaveRequest,
    LeavePerDay, LeaveTransaction, Attendance, Holiday, CustomUser
)
from sms_app.services.leave_service import (
    LeaveValidationService, LeaveWorkflowService, LeaveAllocationService, LeaveAttendanceSyncService
)
from sms_app.services.payroll_service import (
    calculate_leaves, calculate_attendance_days, generate_payslip
)

def run_tests():
    print("=" * 60)
    print("STARTING FULL LEAVE MANAGEMENT & PAYROLL AUDIT TESTS")
    print("=" * 60)

    school = School.objects.filter(id=13).first() or School.objects.first()
    if not school:
        print("ERROR: No school found in database.")
        return

    # Fetch active cycle covering test window
    cycle = LeaveCycle.objects.filter(
        school=school,
        is_active=True,
        is_closed=False,
        start_date__lte=date(2026, 12, 1),
        end_date__gte=date(2026, 12, 31),
    ).first() or LeaveCycle.objects.filter(school=school, is_active=True).first()

    # Create Test Leave Type (Casual Leave, Paid)
    cl_type = LeaveType.objects.filter(name__iexact="AUDIT_CASUAL_LEAVE").first()
    if not cl_type:
        cl_type = LeaveType.objects.create(
            leave_template=None,
            name="AUDIT_CASUAL_LEAVE",
            code="ACL",
            allocation_count=Decimal("12.0"),
            allocation_period="Yearly",
            is_paid=True,
            carry_forward=True,
            max_carry_forward=5,
            half_day_allowed=True,
            include_weekends=False,
            include_holidays=False,
            is_active=True,
        )

    # Create Test Users & Staff
    teacher_user, _ = CustomUser.objects.get_or_create(
        username="audit_teacher_user",
        defaults={"role": "TEACHER", "school": school}
    )
    teacher_staff, _ = Staff.objects.get_or_create(
        user=teacher_user,
        defaults={"name": "Audit Teacher", "category": "TEACHER", "school": school, "is_active": True}
    )

    vp_user, _ = CustomUser.objects.get_or_create(
        username="audit_vp_user",
        defaults={"role": "VICE PRINCIPAL", "school": school}
    )
    vp_staff, _ = Staff.objects.get_or_create(
        user=vp_user,
        defaults={"name": "Audit VP", "category": "VICE PRINCIPAL", "school": school, "is_active": True}
    )

    principal_user, _ = CustomUser.objects.get_or_create(
        username="audit_principal_user",
        defaults={"role": "PRINCIPAL", "school": school}
    )
    principal_staff, _ = Staff.objects.get_or_create(
        user=principal_user,
        defaults={"name": "Audit Principal", "category": "PRINCIPAL", "school": school, "is_active": True}
    )

    trustee_user, _ = CustomUser.objects.get_or_create(
        username="audit_trustee_user",
        defaults={"role": "TRUSTEE", "school": school}
    )

    print("\n--- TEST 1: LEAVE CALCULATION API & EVENTS/HOLIDAYS CALENDAR ---")
    # Friday to Monday range (Dec 4 to Dec 7, 2026)
    # Dec 4 = Friday (Holiday)
    # Dec 5 = Saturday (Working)
    # Dec 6 = Sunday (Weekend)
    # Dec 7 = Monday (Working)
    holiday, h_created = Holiday.objects.get_or_create(
        school=school,
        name="Audited Dec Holiday",
        start_date=date(2026, 12, 4),
        defaults={"is_holiday": True, "end_date": date(2026, 12, 4)}
    )

    breakdown = LeaveValidationService.get_effective_leave_breakdown(
        school=school,
        leave_type=cl_type,
        start_date=date(2026, 12, 4),
        end_date=date(2026, 12, 7),
    )
    assert breakdown["calendar_days"] == 4, f"Expected 4 calendar days, got {breakdown['calendar_days']}"
    assert breakdown["excluded_holidays"] == 1, f"Expected 1 excluded holiday, got {breakdown['excluded_holidays']}"
    assert breakdown["excluded_weekends"] == 1, f"Expected 1 excluded weekend, got {breakdown['excluded_weekends']}"
    assert breakdown["total_effective_days"] == Decimal("2.0"), f"Expected 2.0 effective days, got {breakdown['total_effective_days']}"
    print("[PASS] Friday-to-Monday with Holiday & Weekend exclusion: PASSED (2.0 working days out of 4)")

    # Date range error check
    try:
        LeaveValidationService.get_effective_leave_breakdown(
            school=school, leave_type=cl_type,
            start_date=date(2026, 12, 10), end_date=date(2026, 12, 5)
        )
        assert False, "Should have raised ValidationError for inverted date range"
    except ValidationError:
        print("[PASS] Inverted date range (start > end) validation: PASSED (Rejected)")

    print("\n--- TEST 2: SPECIAL EDGE CASE 2: HOLIDAY + HALF-DAY ---")
    # Half-day on Sunday
    sunday_half = LeaveValidationService.get_effective_leave_breakdown(
        school=school, leave_type=cl_type,
        start_date=date(2026, 12, 6), end_date=date(2026, 12, 6),
        is_half_day=True, half_day_session="FIRST_HALF"
    )
    assert sunday_half["total_effective_days"] == Decimal("0.0"), "Sunday half-day must have 0 effective days"
    assert len(sunday_half["effective_days"]) == 0, "Sunday half-day must have empty effective days list"
    print("[PASS] Half-day on Sunday: PASSED (0.0 effective days, excluded by weekend policy)")

    # Half-day on Holiday
    holiday_half = LeaveValidationService.get_effective_leave_breakdown(
        school=school, leave_type=cl_type,
        start_date=date(2026, 12, 4), end_date=date(2026, 12, 4),
        is_half_day=True, half_day_session="FIRST_HALF"
    )
    assert holiday_half["total_effective_days"] == Decimal("0.0"), "Holiday half-day must have 0 effective days"
    print("[PASS] Half-day on Holiday: PASSED (0.0 effective days, excluded by holiday calendar)")

    print("\n--- TEST 3: BALANCE & CONCURRENCY CONTROL ---")
    # Reset teacher balance to 2 available
    bal, _ = LeaveBalance.objects.get_or_create(
        staff=teacher_staff, leave_type=cl_type, leave_cycle=cycle,
        defaults={"allocated": Decimal("2.0"), "carry_forward": Decimal("0.0"), "used": Decimal("0.0"), "pending": Decimal("0.0")}
    )
    bal.allocated = Decimal("2.0")
    bal.carry_forward = Decimal("0.0")
    bal.used = Decimal("0.0")
    bal.pending = Decimal("0.0")
    bal.save()

    # Clean existing leave days in test window
    LeavePerDay.objects.filter(leave__staff__in=[teacher_staff, principal_staff]).delete()
    LeaveRequest.objects.filter(staff__in=[teacher_staff, principal_staff]).delete()
    Attendance.objects.filter(staff__in=[teacher_staff, principal_staff], attendance_date__gte=date(2026, 12, 1)).delete()

    # Request 1 takes 2 days (Dec 8 to Dec 9, 2026 - Tue & Wed)
    req1 = LeaveWorkflowService.submit_leave_request(
        staff=teacher_staff, school=school, leave_type=cl_type,
        start_date=date(2026, 12, 8), end_date=date(2026, 12, 9),
        reason="Testing concurrency request 1", requested_by=teacher_user
    )
    bal.refresh_from_db()
    assert bal.pending == Decimal("2.0"), f"Expected pending 2.0, got {bal.pending}"
    assert bal.available == Decimal("0.0"), f"Expected available 0.0, got {bal.available}"
    print(f"[PASS] Request 1 submitted: balance reserved atomically (Available: {bal.available})")

    # Request 2 arrives trying to take another 2 days
    try:
        LeaveWorkflowService.submit_leave_request(
            staff=teacher_staff, school=school, leave_type=cl_type,
            start_date=date(2026, 12, 10), end_date=date(2026, 12, 11),
            reason="Testing concurrency request 2", requested_by=teacher_user
        )
        assert False, "Should have failed due to insufficient balance"
    except ValidationError as e:
        print(f"[PASS] Concurrent Request 2 blocked: PASSED ({e})")

    print("\n--- TEST 4: APPROVAL PERMISSIONS & HIERARCHY ---")
    # Teacher -> Principal approval
    LeaveWorkflowService.approve_leave_request(req1, principal_user, school)
    req1.refresh_from_db()
    assert req1.status == "APPROVED", "Teacher leave must be approved by Principal"
    print("[PASS] Teacher -> Principal approval: PASSED (Approved)")

    # Principal submits leave
    p_bal, _ = LeaveBalance.objects.get_or_create(
        staff=principal_staff, leave_type=cl_type, leave_cycle=cycle,
        defaults={"allocated": Decimal("10.0"), "carry_forward": Decimal("0.0"), "used": Decimal("0.0"), "pending": Decimal("0.0")}
    )
    p_bal.allocated = Decimal("10.0")
    p_bal.pending = Decimal("0.0")
    p_bal.used = Decimal("0.0")
    p_bal.save()

    p_req = LeaveWorkflowService.submit_leave_request(
        staff=principal_staff, school=school, leave_type=cl_type,
        start_date=date(2026, 12, 15), end_date=date(2026, 12, 16),
        reason="Principal personal leave", requested_by=principal_user
    )

    # 1. Principal self-approval attempt (MUST BE BLOCKED)
    try:
        LeaveWorkflowService.approve_leave_request(p_req, principal_user, school)
        assert False, "Principal self-approval must be blocked"
    except PermissionDenied as e:
        print(f"[PASS] Principal self-approval blocked: PASSED ({e})")

    # 2. Vice Principal approval attempt on Principal's leave (MUST BE BLOCKED)
    try:
        LeaveWorkflowService.approve_leave_request(p_req, vp_user, school)
        assert False, "Vice Principal must not approve Principal leave"
    except PermissionDenied as e:
        print(f"[PASS] Vice Principal approval of Principal leave blocked: PASSED ({e})")

    # 3. Trustee approval on Principal's leave (MUST SUCCEED)
    LeaveWorkflowService.approve_leave_request(p_req, trustee_user, school)
    p_req.refresh_from_db()
    assert p_req.status == "APPROVED", "Trustee must be able to approve Principal leave"
    print("[PASS] Principal -> Trustee approval: PASSED (Approved by Trustee)")

    print("\n--- TEST 5: ATTENDANCE & PAYROLL INTEGRATION (SPECIAL EDGE CASE 1) ---")
    # Edge Case 1: Same day Half-Day Leave + Half-Day Attendance
    # Date: 2026-12-18 (Friday)
    test_date = date(2026, 12, 18)
    bal.allocated = Decimal("10.0")
    bal.pending = Decimal("0.0")
    bal.used = Decimal("0.0")
    bal.save()

    half_req = LeaveWorkflowService.submit_leave_request(
        staff=teacher_staff, school=school, leave_type=cl_type,
        start_date=test_date, end_date=test_date,
        is_half_day=True, half_day_session="FIRST_HALF",
        reason="Half day morning leave", requested_by=teacher_user
    )
    LeaveWorkflowService.approve_leave_request(half_req, principal_user, school)
    half_req.refresh_from_db()
    bal.refresh_from_db()
    assert bal.used == Decimal("0.5"), f"Expected used 0.5, got {bal.used}"
    print("[PASS] Half-day leave balance deduction: PASSED (exactly 0.5 deducted)")

    # Simulate second half punch attendance
    att = Attendance.objects.filter(staff=teacher_staff, attendance_date=test_date).first()
    assert att is not None, "Attendance record must be synced"
    assert att.canonical_status == "HALF_DAY", f"Expected HALF_DAY status, got {att.canonical_status}"
    att.is_present = True  # Teacher punched in for afternoon session
    att.is_half_day = True
    att.save()

    paid_days, unpaid_days = calculate_leaves(teacher_staff, test_date, test_date)
    pres_days, half_days, late_cnt = calculate_attendance_days(teacher_staff, test_date, test_date)

    assert paid_days == Decimal("0.5"), f"Expected 0.5 paid leave, got {paid_days}"
    assert half_days == Decimal("1.0"), f"Expected 1.0 half-day attendance, got {half_days}"
    total_payable_day = pres_days + paid_days + (half_days * Decimal("0.5"))
    assert total_payable_day == Decimal("1.0"), f"Expected 1.0 total payable day, got {total_payable_day}"
    print(f"[PASS] Half-day Attendance (0.5) + Half-day Paid Leave (0.5) = {total_payable_day} Full Payable Day: PASSED (No duplicate deduction)")

    print("\n--- TEST 6: APPROVED LEAVE CANCELLATION (SPECIAL EDGE CASE 3) ---")
    # Cancel half_req
    LeaveWorkflowService.request_cancellation(half_req, teacher_user, "Plans cancelled")
    half_req.refresh_from_db()
    assert half_req.cancellation_status == "REQUESTED", "Cancellation must be requested"

    LeaveWorkflowService.approve_cancellation(half_req, principal_user, school)
    half_req.refresh_from_db()
    bal.refresh_from_db()
    assert half_req.status == "CANCELLED", "Leave must be CANCELLED"
    assert bal.used == Decimal("0.0"), f"Expected used balance refunded to 0.0, got {bal.used}"
    print("[PASS] Approved leave cancellation: used balance refunded to employee: PASSED")

    print("\n--- TEST 7: CARRY FORWARD & REPEATED ALLOCATION IDEMPOTENCY ---")
    # Repeated allocation check
    res1 = LeaveAllocationService.allocate_leaves_for_staff(teacher_staff, cycle)
    res2 = LeaveAllocationService.allocate_leaves_for_staff(teacher_staff, cycle)
    assert len(res2) == 0, "Repeated allocation must be idempotent and not create duplicate balances"
    print("[PASS] Repeated allocation idempotency: PASSED (0 duplicate balances created)")

    print("\n" + "=" * 60)
    print("ALL AUDIT TESTS PASSED SUCCESSFULLY! ZERO ISSUES FOUND.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
