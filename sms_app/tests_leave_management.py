from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
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
    AttendanceSetting,
    Holiday,
    StaffRemainingLeave,
)
from sms_app.services.leave_service import (
    LeaveValidationService,
    LeaveWorkflowService,
    LeaveAttendanceSyncService,
    LeaveAllocationService,
    LeaveCycleClosingService,
)

User = get_user_model()


class LeaveManagementComprehensiveTestCase(TestCase):
    def setUp(self):
        # 1. Setup School A and School B for tenant isolation
        self.user_a = User.objects.create_user(username="admin_a", email="admin_a@school.com", password="pass")
        self.school_a = School.objects.create(name="School Alpha", code="SCH_A", login_id=self.user_a)

        self.user_b = User.objects.create_user(username="admin_b", email="admin_b@school.com", password="pass")
        self.school_b = School.objects.create(name="School Beta", code="SCH_B", login_id=self.user_b)

        # 2. Setup Principal and Teacher users for School A
        self.principal_user = User.objects.create_user(
            username="principal_a",
            email="principal@school.com",
            role="PRINCIPAL",
            school=self.school_a,
        )
        self.principal_staff = Staff.objects.create(
            name="Principal Sharma",
            user=self.principal_user,
            school=self.school_a,
            category="PRINCIPAL",
            is_active=True,
            joining_date=date(2025, 1, 1),
        )

        self.teacher_user = User.objects.create_user(
            username="teacher_a",
            email="teacher@school.com",
            role="TEACHER",
            school=self.school_a,
        )
        self.teacher_staff = Staff.objects.create(
            name="Teacher Patel",
            user=self.teacher_user,
            school=self.school_a,
            category="TEACHER",
            is_active=True,
            joining_date=date(2026, 1, 1),
        )

        # 3. Setup Leave Cycle 2026-2027
        self.cycle_2026 = LeaveCycle.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_active=True,
        )

        # 4. Setup Leave Template & Leave Types
        self.template = LeaveTemplate.objects.create(
            school=self.school_a,
            name="Standard Teaching Staff Policy",
            time_line="ANNUAL",
            is_active=True,
        )
        self.teacher_staff.leave_template = self.template
        self.teacher_staff.save()

        # Casual Leave: 12 days, carry forward allowed up to 5 days, half-day allowed
        self.cl_type = LeaveType.objects.create(
            leave_template=self.template,
            name="Casual Leave",
            leave_type="CASUAL_LEAVE",
            code="CL",
            is_paid=True,
            allocation_count=Decimal("12.0"),
            allocation_period="Yearly",
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

        # Sick Leave: 10 days, no carry forward
        self.sl_type = LeaveType.objects.create(
            leave_template=self.template,
            name="Sick Leave",
            leave_type="SICK_LEAVE",
            code="SL",
            is_paid=True,
            allocation_count=Decimal("10.0"),
            allocation_period="Yearly",
            carry_forward=False,
            half_day_allowed=False,
            include_weekends=False,
            include_holidays=False,
            allow_negative_balance=False,
            allow_future_leave=True,
            allow_backdated_leave=True,
            max_backdated_days=14,
            prorata_on_joining="PRO_RATA",
        )

        # Initialize teacher balance: 12 CL allocated
        self.cl_balance = LeaveBalance.objects.create(
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            leave_cycle=self.cycle_2026,
            opening_balance=Decimal("0.0"),
            allocated=Decimal("12.0"),
            carry_forward=Decimal("0.0"),
            used=Decimal("0.0"),
            pending=Decimal("0.0"),
        )

    def test_01_leave_submission_and_balance_reservation(self):
        """Test submitting leave correctly reserves pending balance."""
        start = date(2026, 11, 2)  # Monday
        end = date(2026, 11, 4)    # Wednesday (3 days)

        leave_req = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=start,
            end_date=end,
            reason="Family function",
            requested_by=self.teacher_user,
        )

        self.assertEqual(leave_req.status, "PENDING")
        self.assertEqual(leave_req.total_days, Decimal("3.0"))
        self.assertEqual(leave_req.leave_days.count(), 3)

        # Check balance reservation
        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("3.0"))
        self.assertEqual(self.cl_balance.available, Decimal("9.0"))

        # Verify transaction logged
        tx = LeaveTransaction.objects.filter(leave_request=leave_req, transaction_type="RESERVATION").first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, Decimal("3.0"))

    def test_02_withdrawal_releases_balance(self):
        """Test withdrawing a pending leave request releases the reserved balance."""
        start = date(2026, 11, 10)
        end = date(2026, 11, 11)  # 2 days

        leave_req = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=start,
            end_date=end,
            reason="Personal work",
            requested_by=self.teacher_user,
        )

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("2.0"))

        # Withdraw
        LeaveWorkflowService.withdraw_leave_request(leave_req, self.teacher_user)

        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, "CANCELLED")

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("0.0"))
        self.assertEqual(self.cl_balance.available, Decimal("12.0"))

    def test_03_principal_approval_and_attendance_sync(self):
        """Test approval by Principal updates balance, attendance, and prevents self-approval."""
        start = date(2026, 11, 16)
        end = date(2026, 11, 17)  # 2 days

        leave_req = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=start,
            end_date=end,
            reason="Attending seminar",
            requested_by=self.teacher_user,
        )

        # 1. Attempt Self-Approval by Teacher -> MUST FAIL
        with self.assertRaises(PermissionDenied):
            LeaveWorkflowService.approve_leave_request(leave_req, self.teacher_user, self.school_a)

        # 2. Attempt Approval for different school -> MUST FAIL
        with self.assertRaises(PermissionDenied):
            LeaveWorkflowService.approve_leave_request(leave_req, self.principal_user, self.school_b)

        # 3. Legitimate Approval by Principal
        LeaveWorkflowService.approve_leave_request(leave_req, self.principal_user, self.school_a)

        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, "APPROVED")
        self.assertEqual(leave_req.approved_by, self.principal_user)

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("0.0"))
        self.assertEqual(self.cl_balance.used, Decimal("2.0"))
        self.assertEqual(self.cl_balance.available, Decimal("10.0"))

        # Verify Attendance records synchronized with source='Leave'
        att_records = Attendance.objects.filter(staff=self.teacher_staff, attendance_date__in=[start, end])
        self.assertEqual(att_records.count(), 2)
        for att in att_records:
            self.assertFalse(att.is_present)
            self.assertEqual(att.source, "Leave")

    def test_04_insufficient_balance_rejection(self):
        """Test requesting more than available balance is rejected when negative balance disabled."""
        start = date(2026, 12, 1)
        end = date(2026, 12, 20)  # ~16 working days > 12 available

        with self.assertRaises(ValidationError) as ctx:
            LeaveWorkflowService.submit_leave_request(
                staff=self.teacher_staff,
                school=self.school_a,
                leave_type=self.cl_type,
                start_date=start,
                end_date=end,
                reason="Long trip",
                requested_by=self.teacher_user,
            )
        self.assertIn("Insufficient leave balance", str(ctx.exception))

    def test_05_half_day_sessions_and_overlap_collision(self):
        """Test half-day FIRST_HALF and SECOND_HALF coexist, but collisions are blocked."""
        target_date = date(2026, 11, 25)

        # Submit FIRST_HALF
        req1 = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=target_date,
            end_date=target_date,
            reason="Morning appointment",
            is_half_day=True,
            half_day_session="FIRST_HALF",
            requested_by=self.teacher_user,
        )
        self.assertEqual(req1.total_days, Decimal("0.5"))

        # Conflicting request: another FIRST_HALF on same day -> MUST FAIL
        with self.assertRaises(ValidationError) as ctx:
            LeaveWorkflowService.submit_leave_request(
                staff=self.teacher_staff,
                school=self.school_a,
                leave_type=self.cl_type,
                start_date=target_date,
                end_date=target_date,
                reason="Duplicate morning request",
                is_half_day=True,
                half_day_session="FIRST_HALF",
                requested_by=self.teacher_user,
            )
        self.assertIn("collision", str(ctx.exception).lower() or "active half-day leave")

        # Compatible request: SECOND_HALF on same day -> ALLOWED!
        req2 = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=target_date,
            end_date=target_date,
            reason="Afternoon doctor appointment",
            is_half_day=True,
            half_day_session="SECOND_HALF",
            requested_by=self.teacher_user,
        )
        self.assertEqual(req2.total_days, Decimal("0.5"))

    def test_06_holidays_and_weekends_exclusion(self):
        """Test holidays and Sunday weekends are not counted towards leave when excluded by policy."""
        # Setup Holiday on 2026-11-06 (Friday)
        Holiday.objects.create(
            school=self.school_a,
            name="Diwali Holiday",
            is_holiday=True,
            start_date=date(2026, 11, 6),
            end_date=date(2026, 11, 6),
        )

        # Request from Friday (Nov 6) to Monday (Nov 9)
        # Nov 6 = Holiday (excluded)
        # Nov 7 = Saturday (working)
        # Nov 8 = Sunday (weekend excluded)
        # Nov 9 = Monday (working)
        # Total effective days should be 2 days (Nov 7 and Nov 9)!
        effective = LeaveValidationService.get_effective_leave_days(
            self.school_a,
            self.cl_type,
            date(2026, 11, 6),
            date(2026, 11, 9),
        )
        self.assertEqual(len(effective), 2)
        effective_dates = [d[0] for d in effective]
        self.assertNotIn(date(2026, 11, 6), effective_dates)
        self.assertNotIn(date(2026, 11, 8), effective_dates)
        self.assertIn(date(2026, 11, 7), effective_dates)
        self.assertIn(date(2026, 11, 9), effective_dates)

    def test_07_cancellation_workflow_and_refund(self):
        """Test approved leave cancellation request, approver refund, and attendance reversion."""
        start = date(2026, 12, 10)
        end = date(2026, 12, 11)  # 2 days

        leave_req = LeaveWorkflowService.submit_leave_request(
            staff=self.teacher_staff,
            school=self.school_a,
            leave_type=self.cl_type,
            start_date=start,
            end_date=end,
            reason="Urgent travel",
            requested_by=self.teacher_user,
        )
        LeaveWorkflowService.approve_leave_request(leave_req, self.principal_user, self.school_a)

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.used, Decimal("2.0"))
        self.assertEqual(self.cl_balance.available, Decimal("10.0"))

        # Teacher requests cancellation
        LeaveWorkflowService.request_cancellation(leave_req, self.teacher_user, "Event was postponed")
        leave_req.refresh_from_db()
        self.assertEqual(leave_req.cancellation_status, "REQUESTED")

        # Self-approval of cancellation -> MUST FAIL
        with self.assertRaises(PermissionDenied):
            LeaveWorkflowService.approve_cancellation(leave_req, self.teacher_user, self.school_a)

        # Principal approves cancellation
        LeaveWorkflowService.approve_cancellation(leave_req, self.principal_user, self.school_a)
        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, "CANCELLED")
        self.assertEqual(leave_req.cancellation_status, "APPROVED")

        # Balance refunded!
        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.used, Decimal("0.0"))
        self.assertEqual(self.cl_balance.available, Decimal("12.0"))

        # Attendance record reverted
        self.assertFalse(Attendance.objects.filter(staff=self.teacher_staff, attendance_date=start).exists())

    def test_08_pro_rata_joining_date_allocation(self):
        """Test staff joining midway through the cycle receives prorated allocation."""
        # Create new staff joining on Oct 1, 2026 (halfway through April 2026 - March 2027 cycle)
        mid_staff = Staff.objects.create(
            name="Midyear Joinee",
            school=self.school_a,
            category="TEACHER",
            joining_date=date(2026, 10, 1),
            leave_template=self.template,
            is_active=True,
        )

        allocs = LeaveAllocationService.allocate_leaves_for_staff(mid_staff, self.cycle_2026)
        self.assertTrue(len(allocs) > 0)

        # For Casual Leave (12 days total for 365 days):
        # Remaining cycle days from Oct 1 to March 31 = 182 days (~50%)
        # Allocation should be prorated to approximately 6.0 days!
        bal = LeaveBalance.objects.get(staff=mid_staff, leave_type=self.cl_type, leave_cycle=self.cycle_2026)
        self.assertEqual(bal.allocated, Decimal("6.0"))

        # Test idempotency: calling allocation again should NOT duplicate
        allocs2 = LeaveAllocationService.allocate_leaves_for_staff(mid_staff, self.cycle_2026)
        self.assertEqual(len(allocs2), 0)
        bal.refresh_from_db()
        self.assertEqual(bal.allocated, Decimal("6.0"))

    def test_09_cycle_closing_and_carry_forward(self):
        """Test closing cycle transfers carry forward within limit and expires remainder."""
        # Teacher has 12 CL allocated, used 2 CL -> 10 CL unused
        self.cl_balance.used = Decimal("2.0")
        self.cl_balance.save()

        # Next Cycle: 2027-2028
        cycle_2027 = LeaveCycle.objects.create(
            school=self.school_a,
            name="2027-2028",
            start_date=date(2027, 4, 1),
            end_date=date(2028, 3, 31),
            is_active=False,
        )

        # Close cycle: CL allows max_carry_forward=5
        # 10 unused -> 5 carried forward, 5 expired!
        LeaveCycleClosingService.close_cycle(self.cycle_2026, cycle_2027, user=self.principal_user)

        self.cycle_2026.refresh_from_db()
        self.assertTrue(self.cycle_2026.is_closed)
        cycle_2027.refresh_from_db()
        self.assertTrue(cycle_2027.is_active)

        # Check balance in 2027-2028
        next_bal = LeaveBalance.objects.get(staff=self.teacher_staff, leave_type=self.cl_type, leave_cycle=cycle_2027)
        self.assertEqual(next_bal.carry_forward, Decimal("5.0"))

        # Verify EXPIRY and CARRY_FORWARD transactions logged
        exp_tx = LeaveTransaction.objects.filter(staff=self.teacher_staff, transaction_type="EXPIRY").first()
        self.assertIsNotNone(exp_tx)
        self.assertEqual(exp_tx.amount, Decimal("5.0"))

        cf_tx = LeaveTransaction.objects.filter(staff=self.teacher_staff, transaction_type="CARRY_FORWARD").first()
        self.assertIsNotNone(cf_tx)
        self.assertEqual(cf_tx.amount, Decimal("5.0"))

        # Test idempotency: closing an already closed cycle should raise error
        with self.assertRaises(ValidationError):
            LeaveCycleClosingService.close_cycle(self.cycle_2026, cycle_2027, user=self.principal_user)

    def test_10_leave_balance_write_protection(self):
        """Security Test: LeaveBalance cannot be mutated via API/serializer writes."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
        from sms_app.dynamic_hr_views import LeaveBalanceViewSet
        from sms_app.dynamic_hr_serializers import LeaveBalanceSerializer

        factory = APIRequestFactory()

        # 1. Direct create on LeaveBalanceViewSet must be forbidden
        view = LeaveBalanceViewSet.as_view({"post": "create"})
        request = factory.post("/api/leave-balances/", {
            "staff": self.teacher_staff.id,
            "leave_type": self.cl_type.id,
            "leave_cycle": self.cycle_2026.id,
            "allocated": "999.0",
        })
        force_authenticate(request, user=self.teacher_user)
        with self.assertRaises(DRFPermissionDenied):
            view(request)

        # 2. Direct update on LeaveBalanceViewSet must be forbidden
        view_update = LeaveBalanceViewSet.as_view({"put": "update", "patch": "partial_update"})
        request_patch = factory.patch(f"/api/leave-balances/{self.cl_balance.id}/", {
            "allocated": "999.0",
            "used": "0.0",
        })
        force_authenticate(request_patch, user=self.teacher_user)
        with self.assertRaises(DRFPermissionDenied):
            view_update(request_patch, pk=self.cl_balance.id)

        # 3. Direct delete on LeaveBalanceViewSet must be forbidden
        view_delete = LeaveBalanceViewSet.as_view({"delete": "destroy"})
        request_del = factory.delete(f"/api/leave-balances/{self.cl_balance.id}/")
        force_authenticate(request_del, user=self.teacher_user)
        with self.assertRaises(DRFPermissionDenied):
            view_delete(request_del, pk=self.cl_balance.id)

        # 4. LeaveBalanceSerializer ignores attempts to write server-managed fields
        serializer = LeaveBalanceSerializer(
            instance=self.cl_balance,
            data={"allocated": "999.0", "used": "0.0", "opening_balance": "500.0", "carry_forward": "200.0"},
            partial=True,
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data, {})  # All fields stripped because they are read-only!

    def test_11_leave_approval_field_protection_and_self_approval(self):
        """Security Test: Users cannot self-approve leave requests through serializer/API."""
        from rest_framework.test import APIRequestFactory, force_authenticate
        from sms_app.library_leave_serializers import LeaveRequestSerializer, ChangeLeavePerDaySerializer
        from sms_app.library_leave_views import LeaveRequestView, ChangeLeaveView

        factory = APIRequestFactory()

        # 1. LeaveRequestSerializer strips status='APPROVED' and creates request as PENDING
        request = factory.post("/api/leave-request/")
        request.user = self.teacher_user
        serializer = LeaveRequestSerializer(
            data={
                "leave_type": self.cl_type.id,
                "dynamic_leave_type": self.cl_type.id,
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
                "reason": "Family function",
                "status": "APPROVED",
                "approved_by": self.teacher_user.id,
                "approved_at": timezone.now().isoformat(),
            },
            context={"request": request},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_req = serializer.save()
        self.assertEqual(created_req.status, "PENDING")
        self.assertIsNone(created_req.approved_by)
        self.assertIsNone(created_req.approved_at)

        # 2. Prevent self-approval via LeaveWorkflowService
        with self.assertRaises(PermissionDenied):
            LeaveWorkflowService.approve_leave_request(created_req, self.teacher_user, self.school_a)

        # 3. Prevent day-wise self-approval on ChangeLeavePerDaySerializer
        day_rec = created_req.leave_days.first()
        self.assertIsNotNone(day_rec)
        req_day = factory.patch(f"/api/change-leave-status/{day_rec.id}/")
        req_day.user = self.teacher_user
        day_serializer = ChangeLeavePerDaySerializer(
            instance=day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_day},
        )
        self.assertFalse(day_serializer.is_valid())
        self.assertIn("Self-approval is strictly forbidden", str(day_serializer.errors))

        # 4. Legitimate approval by authorized principal succeeds
        LeaveWorkflowService.approve_leave_request(created_req, self.principal_user, self.school_a)
        created_req.refresh_from_db()
        self.assertEqual(created_req.status, "APPROVED")
        self.assertEqual(created_req.approved_by, self.principal_user)
        self.assertIsNotNone(created_req.approved_at)

    def test_12_half_day_unpaid_leave_calculation(self):
        """Test that get_approved_paid_leave_days aggregates day_weight correctly (0.5 for half day, 1.0 for full day)."""
        from sms_app.library_leave_views import get_approved_paid_leave_days

        # Create an unpaid leave type (Loss of Pay)
        lop_type = LeaveType.objects.create(
            leave_template=self.template,
            name="Loss of Pay",
            leave_type="UNPAID_LEAVE",
            is_paid=False,
            allocation_count=Decimal("0.0"),
        )
        lop_req = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=lop_type,
            dynamic_leave_type=lop_type,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 3),
            total_days=Decimal("1.5"),
            status="APPROVED",
            is_paid=False,
        )

        # 1. Full day approved unpaid leave (day_weight = 1.0)
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=lop_req,
            date=date(2026, 7, 1),
            status="APPROVED",
            day_weight=Decimal("1.0"),
            session="FULL_DAY",
        )
        # 2. Half day approved unpaid leave (day_weight = 0.5)
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=lop_req,
            date=date(2026, 7, 2),
            status="APPROVED",
            day_weight=Decimal("0.5"),
            session="FIRST_HALF",
        )
        # 3. Pending unpaid leave day on July 3 (should NOT count)
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=lop_req,
            date=date(2026, 7, 3),
            status="PENDING",
            day_weight=Decimal("0.5"),
            session="SECOND_HALF",
        )

        # Total approved unpaid days = 1.0 + 0.5 = 1.5
        deduction_days = get_approved_paid_leave_days(self.teacher_staff, date(2026, 7, 1), date(2026, 7, 31))
        self.assertEqual(deduction_days, Decimal("1.5"))

        # Empty range returns Decimal("0.0")
        zero_days = get_approved_paid_leave_days(self.teacher_staff, date(2026, 8, 1), date(2026, 8, 31))
        self.assertEqual(zero_days, Decimal("0.0"))

    def test_13_day_level_approval_balance_weight(self):
        """Test ChangeLeavePerDaySerializer uses day_weight for balance deduction and avoids double deductions."""
        from rest_framework.test import APIRequestFactory
        from sms_app.library_leave_serializers import ChangeLeavePerDaySerializer

        factory = APIRequestFactory()

        # Balance initialized: pending=1.5, used=0.0
        self.cl_balance.pending = Decimal("1.5")
        self.cl_balance.used = Decimal("0.0")
        self.cl_balance.save()

        leave_req = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 2),
            total_days=Decimal("1.5"),
            status="PENDING",
        )
        # Half-day record (day_weight = 0.5)
        half_day_rec = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 9, 1),
            status="PENDING",
            day_weight=Decimal("0.5"),
            session="FIRST_HALF",
        )

        req_principal = factory.patch(f"/api/change-leave-status/{half_day_rec.id}/")
        req_principal.user = self.principal_user

        # 1. Approve half-day record -> decrements pending by 0.5, increments used by 0.5
        serializer = ChangeLeavePerDaySerializer(
            instance=half_day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("1.0"))  # 1.5 - 0.5 = 1.0 (NOT 0.5!)
        self.assertEqual(self.cl_balance.used, Decimal("0.5"))     # 0.0 + 0.5 = 0.5 (NOT 1.0!)

        # 2. Repeated approval (idempotency check) -> must NOT deduct again
        half_day_rec.refresh_from_db()
        serializer_repeat = ChangeLeavePerDaySerializer(
            instance=half_day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_repeat.is_valid())
        serializer_repeat.save()

        self.cl_balance.refresh_from_db()
        self.assertEqual(self.cl_balance.pending, Decimal("1.0"))
        self.assertEqual(self.cl_balance.used, Decimal("0.5"))

        # 3. StaffRemainingLeave compatibility: legacy integer field is NOT corrupted with Decimals on half-day
        legacy_rem = StaffRemainingLeave.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_template=self.template,
            leave_type=self.cl_type,
            total_levaes=10,
            remaining_leaves=10,
        )
        # Approval of half-day (0.5) must leave integer remaining_leaves unchanged (not crash or truncate)
        serializer_half_legacy = ChangeLeavePerDaySerializer(
            instance=half_day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_half_legacy.is_valid())
        serializer_half_legacy.save()
        legacy_rem.refresh_from_db()
        self.assertEqual(legacy_rem.remaining_leaves, 10)  # Untouched on 0.5; preserves integer semantics

        # 4. Whole-day approval decrements legacy remaining_leaves by exact integer
        full_day_rec = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 9, 2),
            status="PENDING",
            day_weight=Decimal("1.0"),
            session="FULL_DAY",
        )
        serializer_full = ChangeLeavePerDaySerializer(
            instance=full_day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_full.is_valid(), serializer_full.errors)
        serializer_full.save()
        legacy_rem.refresh_from_db()
        self.assertEqual(legacy_rem.remaining_leaves, 9)  # 10 - 1 = 9 (exact integer)

        # 5. Invalid zero-weight day is rejected (not silently converted to 1.0)
        zero_day_rec = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 9, 3),
            status="PENDING",
            day_weight=Decimal("0.0"),
            session="FULL_DAY",
        )
        serializer_zero = ChangeLeavePerDaySerializer(
            instance=zero_day_rec,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertFalse(serializer_zero.is_valid())
        self.assertIn("Day weight must be greater than zero", str(serializer_zero.errors))

    def test_14_day_level_ledger_and_attendance_sync(self):
        """Test Stage 6B: Day-level approval, rejection, and cancellation maintain LeaveTransaction and Attendance."""
        from rest_framework.test import APIRequestFactory
        from sms_app.library_leave_serializers import ChangeLeavePerDaySerializer
        from datetime import time

        factory = APIRequestFactory()

        # 1. Setup fresh balance and request
        self.cl_balance.pending = Decimal("2.0")
        self.cl_balance.used = Decimal("0.0")
        self.cl_balance.save()

        leave_req = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            total_days=Decimal("1.5"),
            status="PENDING",
        )
        half_day = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 10, 1),
            status="PENDING",
            day_weight=Decimal("0.5"),
            session="FIRST_HALF",
        )
        full_day = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 10, 2),
            status="PENDING",
            day_weight=Decimal("1.0"),
            session="FULL_DAY",
        )

        req_principal = factory.patch(f"/api/change-leave-status/{half_day.id}/")
        req_principal.user = self.principal_user

        # 2. Approve half-day -> USAGE transaction for 0.5 & Attendance is_half_day=True
        serializer_half = ChangeLeavePerDaySerializer(
            instance=half_day,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_half.is_valid(), serializer_half.errors)
        serializer_half.save()

        tx_half = LeaveTransaction.objects.filter(
            staff=self.teacher_staff, leave_request=leave_req, transaction_type="USAGE", amount=Decimal("0.5")
        ).first()
        self.assertIsNotNone(tx_half)
        self.assertEqual(tx_half.amount, Decimal("0.5"))

        att_half = Attendance.objects.filter(staff=self.teacher_staff, attendance_date=date(2026, 10, 1)).first()
        self.assertIsNotNone(att_half)
        self.assertTrue(att_half.is_half_day)
        self.assertEqual(att_half.source, "Leave")

        # 3. Repeated approval of half-day -> No duplicate LeaveTransaction
        tx_count_before = LeaveTransaction.objects.filter(staff=self.teacher_staff, leave_request=leave_req).count()
        serializer_half_repeat = ChangeLeavePerDaySerializer(
            instance=half_day,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_half_repeat.is_valid())
        serializer_half_repeat.save()
        tx_count_after = LeaveTransaction.objects.filter(staff=self.teacher_staff, leave_request=leave_req).count()
        self.assertEqual(tx_count_before, tx_count_after)

        # 4. Existing biometric punches preserved on full-day approval
        punch_att = Attendance.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            attendance_date=date(2026, 10, 2),
            check_in=time(9, 0),
            check_out=time(17, 0),
            is_present=True,
            source="Punch",
        )
        serializer_full = ChangeLeavePerDaySerializer(
            instance=full_day,
            data={"status": "APPROVED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_full.is_valid(), serializer_full.errors)
        serializer_full.save()

        punch_att.refresh_from_db()
        self.assertEqual(punch_att.check_in, time(9, 0))  # Punch preserved!
        self.assertEqual(punch_att.check_out, time(17, 0))
        self.assertEqual(punch_att.source, "Leave")

        # 5. Cancellation of approved day restores punch source and logs CANCELLATION transaction
        serializer_cancel = ChangeLeavePerDaySerializer(
            instance=full_day,
            data={"status": "CANCELLED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_cancel.is_valid(), serializer_cancel.errors)
        serializer_cancel.save()

        punch_att.refresh_from_db()
        self.assertEqual(punch_att.source, "Punch")  # Restored to Punch!
        self.assertTrue(punch_att.is_present)

        tx_cancel = LeaveTransaction.objects.filter(
            staff=self.teacher_staff, leave_request=leave_req, transaction_type="CANCELLATION", amount=Decimal("1.0")
        ).first()
        self.assertIsNotNone(tx_cancel)

        # 6. Cancellation of half-day (without punches) deletes phantom attendance record
        serializer_cancel_half = ChangeLeavePerDaySerializer(
            instance=half_day,
            data={"status": "CANCELLED"},
            partial=True,
            context={"request": req_principal},
        )
        self.assertTrue(serializer_cancel_half.is_valid())
        serializer_cancel_half.save()
        self.assertFalse(Attendance.objects.filter(staff=self.teacher_staff, attendance_date=date(2026, 10, 1)).exists())

    def test_15_payroll_mixed_leave_day_weights(self):
        """Test Priority 3 Payroll calculate_leaves uses authoritative per-day weights for mixed requests."""
        from sms_app.services.payroll_service import calculate_leaves

        # Create 1.5-day paid leave request (1 full day + 1 half day)
        paid_leave = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 11, 2),
            end_date=date(2026, 11, 3),
            total_days=Decimal("1.5"),
            status="APPROVED",
            is_paid=True,
        )
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=paid_leave,
            date=date(2026, 11, 2),
            status="APPROVED",
            day_weight=Decimal("1.0"),
            session="FULL_DAY",
        )
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=paid_leave,
            date=date(2026, 11, 3),
            status="APPROVED",
            day_weight=Decimal("0.5"),
            session="FIRST_HALF",
        )

        # Create 0.5-day unpaid leave request
        unpaid_leave = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 11, 4),
            end_date=date(2026, 11, 4),
            total_days=Decimal("0.5"),
            status="APPROVED",
            is_paid=False,
        )
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=unpaid_leave,
            date=date(2026, 11, 4),
            status="APPROVED",
            day_weight=Decimal("0.5"),
            session="SECOND_HALF",
        )

        paid_days, unpaid_days = calculate_leaves(
            self.teacher_staff, date(2026, 11, 1), date(2026, 11, 30)
        )
        # Authoritative day weights: 1.0 + 0.5 = 1.5 paid days (NOT 2.0!), 0.5 unpaid days
        self.assertEqual(paid_days, Decimal("1.5"))
        self.assertEqual(unpaid_days, Decimal("0.5"))

    def test_16_attendance_reversal_threshold_and_multi_leave(self):
        """Test Attendance reversal preserves punches with threshold awareness and protects complementary leaves."""
        from datetime import time, datetime

        # Setup attendance policy: 120 mins threshold for half day
        policy, _ = AttendanceSetting.objects.get_or_create(
            school=self.school_a,
            defaults={
                "check_in_time": time(9, 0),
                "check_out_time": time(17, 0),
                "grace_period_mins": 15,
                "half_day_threshold_mins": 120,
                "is_active": True,
            },
        )
        policy.half_day_threshold_mins = 120
        policy.save()

        # Scenario A: Punches exceed half-day threshold (check in at 11:30, target 9:00 -> 150 mins late)
        att_late = Attendance.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            attendance_date=date(2026, 11, 10),
            check_in=datetime.combine(date(2026, 11, 10), time(11, 30)),
            check_out=datetime.combine(date(2026, 11, 10), time(17, 0)),
            is_present=False,
            is_half_day=True,
            source="Leave",
        )
        leave_req_a = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 10),
            total_days=Decimal("0.5"),
            status="CANCELLED",
        )
        day_a = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req_a,
            date=date(2026, 11, 10),
            status="CANCELLED",
            day_weight=Decimal("0.5"),
        )
        LeaveAttendanceSyncService.revert_day_attendance(day_a)
        att_late.refresh_from_db()
        self.assertEqual(att_late.source, "Punch")
        self.assertTrue(att_late.is_present)
        # Because late by 150 mins > threshold (120 mins), punch itself warrants half-day!
        self.assertTrue(att_late.is_half_day)

        # Scenario B: Multiple approved leaves on same date (e.g. complementary half-days)
        att_comp = Attendance.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            attendance_date=date(2026, 11, 11),
            is_present=False,
            is_half_day=True,
            source="Leave",
        )
        # Complementary session still APPROVED
        other_leave = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 11, 11),
            end_date=date(2026, 11, 11),
            total_days=Decimal("0.5"),
            status="APPROVED",
        )
        other_day = LeavePerDay.objects.create(
            school=self.school_a,
            leave=other_leave,
            date=date(2026, 11, 11),
            status="APPROVED",
            day_weight=Decimal("0.5"),
            session="SECOND_HALF",
        )
        # Cancelled session
        cancelled_day = LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req_a,
            date=date(2026, 11, 11),
            status="CANCELLED",
            day_weight=Decimal("0.5"),
            session="FIRST_HALF",
        )
        LeaveAttendanceSyncService.revert_day_attendance(cancelled_day)
        att_comp.refresh_from_db()
        # Because other_day is still APPROVED on this date, attendance must retain Leave status!
        self.assertEqual(att_comp.source, "Leave")
        self.assertTrue(att_comp.is_half_day)

    def test_17_concurrency_locking_and_workflow_safety(self):
        """Test LeaveWorkflowService re-reads state under select_for_update preventing double transitions."""
        leave_req = LeaveRequest.objects.create(
            school=self.school_a,
            staff=self.teacher_staff,
            leave_type=self.cl_type,
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 1),
            total_days=Decimal("1.0"),
            status="PENDING",
        )
        LeavePerDay.objects.create(
            school=self.school_a,
            leave=leave_req,
            date=date(2026, 12, 1),
            status="PENDING",
            day_weight=Decimal("1.0"),
        )
        # First approval succeeds
        LeaveWorkflowService.approve_leave_request(leave_req, self.principal_user, self.school_a)
        leave_req.refresh_from_db()
        self.assertEqual(leave_req.status, "APPROVED")

        # Second approval attempt fails with ValidationError under row lock re-check
        with self.assertRaises(ValidationError) as ctx:
            LeaveWorkflowService.approve_leave_request(leave_req, self.principal_user, self.school_a)
        self.assertIn("Only PENDING requests can be approved", str(ctx.exception))

