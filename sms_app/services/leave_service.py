import logging
import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q

from sms_app.models import (
    School,
    Staff,
    LeaveType,
    LeaveCycle,
    LeaveRequest,
    LeavePerDay,
    LeaveBalance,
    LeaveTransaction,
    Attendance,
    AttendanceSetting,
    Holiday,
)

logger = logging.getLogger(__name__)


def quantize_half_day(val):
    """Rounds a decimal value to nearest 0.5 (e.g. 0.0, 0.5, 1.0, 1.5)."""
    if val is None:
        return Decimal("0.0")
    d = Decimal(str(val))
    # Multiply by 2, round to whole integer, divide by 2
    doubled = (d * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return doubled / 2


class LeaveValidationService:
    """
    Validates leave requests against school policies, holidays, week-offs,
    employment dates, and overlapping requests.
    """

    @staticmethod
    def get_effective_leave_days(school, leave_type, start_date, end_date, is_half_day=False, half_day_session="FULL_DAY"):
        """
        Determines the list of actual calendar dates that count as leave days,
        taking into account weekends and school holidays based on leave_type settings.
        Returns list of tuples: [(date, day_weight, session)]
        """
        if start_date > end_date:
            raise ValidationError("Start date cannot be after end date.")

        if is_half_day:
            if start_date != end_date:
                raise ValidationError("Half-day leave must start and end on the same date.")
            if not leave_type.half_day_allowed:
                raise ValidationError(f"Leave type '{leave_type.name or leave_type.leave_type}' does not permit half-day leave.")
            if half_day_session not in ["FIRST_HALF", "SECOND_HALF"]:
                half_day_session = "FIRST_HALF"
            return [(start_date, Decimal("0.5"), half_day_session)]

        # Multi-day or single full-day leave
        holiday_dates = set()
        if not leave_type.include_holidays:
            # Query holidays for this school spanning the range
            # Supports both multi-day holidays (with end_date) and single-day holidays (where end_date is NULL)
            holidays = Holiday.objects.filter(
                Q(school=school),
                Q(is_holiday=True),
                Q(start_date__lte=end_date),
                Q(end_date__gte=start_date) | Q(end_date__isnull=True, start_date__gte=start_date),
            )
            for h in holidays:
                holiday_end = h.end_date or h.start_date
                curr = max(h.start_date, start_date)
                h_end = min(holiday_end, end_date)
                while curr <= h_end:
                    holiday_dates.add(curr)
                    curr += timedelta(days=1)

        result = []
        curr = start_date
        while curr <= end_date:
            is_weekend = (curr.weekday() == 6)  # Sunday
            if is_weekend and not leave_type.include_weekends:
                curr += timedelta(days=1)
                continue

            if curr in holiday_dates and not leave_type.include_holidays:
                curr += timedelta(days=1)
                continue

            result.append((curr, Decimal("1.0"), "FULL_DAY"))
            curr += timedelta(days=1)

        if not result:
            raise ValidationError("Selected date range contains only holidays or weekends excluded by policy.")

        # Check consecutive days limit
        if leave_type.max_consecutive_days > 0 and len(result) > leave_type.max_consecutive_days:
            raise ValidationError(
                f"Maximum consecutive days allowed for {leave_type.name or leave_type.leave_type} is {leave_type.max_consecutive_days} days. (Requested: {len(result)} days)"
            )

        return result

    @staticmethod
    def validate_request_rules(staff, leave_type, start_date, end_date, is_half_day=False):
        """
        Validates date boundaries (future/backdated) and staff employment eligibility.
        """
        today = timezone.localdate()

        # Employment status check
        if not staff.is_active:
            raise ValidationError("Inactive staff members cannot apply for leave.")

        if staff.joining_date and start_date < staff.joining_date:
            raise ValidationError(f"Leave cannot be requested before joining date ({staff.joining_date}).")

        if staff.exit_date and end_date > staff.exit_date:
            raise ValidationError(f"Leave cannot be requested after exit date ({staff.exit_date}).")

        # Future leave check
        if not leave_type.allow_future_leave and start_date > today:
            raise ValidationError(f"Future leave is not allowed for {leave_type.name or leave_type.leave_type}.")

        # Backdated leave check
        if start_date < today:
            if not leave_type.allow_backdated_leave:
                raise ValidationError(f"Backdated leave is not allowed for {leave_type.name or leave_type.leave_type}.")
            days_back = (today - start_date).days
            if leave_type.max_backdated_days > 0 and days_back > leave_type.max_backdated_days:
                raise ValidationError(
                    f"Backdated leave cannot exceed {leave_type.max_backdated_days} days for this leave type. (Requested: {days_back} days ago)"
                )

    @staticmethod
    def check_overlapping_requests(staff, effective_days, exclude_request_id=None):
        """
        Checks if any date in effective_days overlaps with existing active
        (PENDING or APPROVED) leave requests for this staff member.
        Properly handles half-day vs full-day:
        - Two half days on different sessions (FIRST_HALF vs SECOND_HALF) are allowed on the same date.
        - Two full days, or full day + half day, or two half days on the same session are rejected.
        """
        requested_dates = [d[0] for d in effective_days]
        if not requested_dates:
            return

        min_date = min(requested_dates)
        max_date = max(requested_dates)

        existing_days_qs = LeavePerDay.objects.filter(
            leave__staff=staff,
            status__in=["PENDING", "APPROVED"],
            date__gte=min_date,
            date__lte=max_date,
        ).select_related("leave")

        if exclude_request_id:
            existing_days_qs = existing_days_qs.exclude(leave_id=exclude_request_id)

        # Map date -> list of existing sessions
        existing_by_date = {}
        for epd in existing_days_qs:
            existing_by_date.setdefault(epd.date, []).append(epd)

        for req_date, weight, req_session in effective_days:
            if req_date in existing_by_date:
                for existing in existing_by_date[req_date]:
                    ex_session = existing.session or ("FULL_DAY" if existing.day_weight == 1.0 else "FIRST_HALF")
                    
                    if weight == Decimal("1.0") or existing.day_weight == Decimal("1.0"):
                        raise ValidationError(
                            f"Staff already has an active leave request on {req_date} (Status: {existing.status})."
                        )
                    # Both are half-day: check session collision
                    if req_session == ex_session:
                        raise ValidationError(
                            f"Staff already has an active half-day leave for {req_session} on {req_date} (Status: {existing.status})."
                        )


class LeaveWorkflowService:
    """
    Manages the lifecycle of Leave Requests:
    Submission with Balance Reservation, Withdrawal, Approval, Rejection,
    Cancellation Request, and Cancellation Approval with Refunds.
    """

    @staticmethod
    def get_or_create_balance(staff, leave_type, leave_cycle):
        balance, _ = LeaveBalance.objects.get_or_create(
            staff=staff,
            leave_type=leave_type,
            leave_cycle=leave_cycle,
            defaults={
                "opening_balance": Decimal("0.0"),
                "allocated": Decimal(str(leave_type.allocation_count or 0.0)),
                "carry_forward": Decimal("0.0"),
                "used": Decimal("0.0"),
                "pending": Decimal("0.0"),
            },
        )
        return balance

    @classmethod
    @transaction.atomic
    def submit_leave_request(
        cls,
        staff,
        school,
        leave_type,
        start_date,
        end_date,
        reason,
        is_half_day=False,
        half_day_session="FULL_DAY",
        requested_by=None,
    ):
        """
        Submits a new leave request, reserves balance, and logs transaction atomically.
        """
        # 1. Validation rules
        LeaveValidationService.validate_request_rules(staff, leave_type, start_date, end_date, is_half_day)
        effective_days = LeaveValidationService.get_effective_leave_days(
            school, leave_type, start_date, end_date, is_half_day, half_day_session
        )
        LeaveValidationService.check_overlapping_requests(staff, effective_days)

        total_days = sum(d[1] for d in effective_days)

        # 2. Find active LeaveCycle for this school and date
        leave_cycle = LeaveCycle.objects.filter(
            school=school,
            is_active=True,
            is_closed=False,
            start_date__lte=start_date,
            end_date__gte=start_date,
        ).first()

        if not leave_cycle:
            # Fallback to general active cycle
            leave_cycle = LeaveCycle.objects.filter(school=school, is_active=True, is_closed=False).first()
            if not leave_cycle:
                raise ValidationError("No active Leave Cycle found for this school. Please contact Administrator.")

        # 3. Lock LeaveBalance for concurrency protection
        balance = LeaveBalance.objects.select_for_update().filter(
            staff=staff, leave_type=leave_type, leave_cycle=leave_cycle
        ).first()

        if not balance:
            balance = cls.get_or_create_balance(staff, leave_type, leave_cycle)
            # Re-select for update
            balance = LeaveBalance.objects.select_for_update().get(id=balance.id)

        # 4. Check available balance
        available = balance.available
        if total_days > available and not leave_type.allow_negative_balance:
            raise ValidationError(
                f"Insufficient leave balance. Available: {available} days, Requested: {total_days} days."
            )

        # 5. Create LeaveRequest
        leave_req = LeaveRequest.objects.create(
            school=school,
            staff=staff,
            leave_type=leave_type,
            dynamic_leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            total_days=total_days,
            is_half_day=is_half_day,
            half_day_session=half_day_session,
            reason=reason,
            status="PENDING",
            is_paid=leave_type.is_paid,
            audit_log=[
                {
                    "action": "SUBMITTED",
                    "by_user_id": requested_by.id if requested_by else None,
                    "by_user_name": str(requested_by) if requested_by else "System",
                    "timestamp": timezone.now().isoformat(),
                    "total_days": float(total_days),
                }
            ],
        )

        # 6. Create LeavePerDay records
        for d_date, d_weight, d_session in effective_days:
            LeavePerDay.objects.create(
                school=school,
                leave=leave_req,
                date=d_date,
                status="PENDING",
                day_weight=d_weight,
                session=d_session,
            )

        # 7. Reserve balance
        balance.pending = Decimal(str(balance.pending or 0)) + total_days
        balance.save()

        # 8. Record LeaveTransaction
        LeaveTransaction.objects.create(
            school=school,
            staff=staff,
            leave_type=leave_type,
            leave_cycle=leave_cycle,
            leave_request=leave_req,
            transaction_type="RESERVATION",
            amount=total_days,
            balance_after=balance.available,
            description=f"Reserved {total_days} days for Leave Request #{leave_req.id}",
            created_by=requested_by,
        )

        return leave_req

    @classmethod
    @transaction.atomic
    def withdraw_leave_request(cls, leave_req, user):
        """
        Withdraws a pending leave request and releases reserved balance.
        """
        if leave_req.pk:
            leave_req = LeaveRequest.objects.select_for_update().get(pk=leave_req.pk)

        if leave_req.status != "PENDING":
            raise ValidationError(f"Cannot withdraw leave request with status '{leave_req.status}'. Only PENDING requests can be withdrawn.")

        # Find balance and lock
        leave_cycle = LeaveCycle.objects.filter(
            school=leave_req.school,
            start_date__lte=leave_req.start_date,
            end_date__gte=leave_req.start_date,
        ).first() or LeaveCycle.objects.filter(school=leave_req.school, is_active=True).first()

        if leave_cycle:
            balance = LeaveBalance.objects.select_for_update().filter(
                staff=leave_req.staff, leave_type=leave_req.leave_type, leave_cycle=leave_cycle
            ).first()
            if balance:
                balance.pending = max(Decimal("0.0"), Decimal(str(balance.pending or 0)) - leave_req.total_days)
                balance.save()

                LeaveTransaction.objects.create(
                    school=leave_req.school,
                    staff=leave_req.staff,
                    leave_type=leave_req.leave_type,
                    leave_cycle=leave_cycle,
                    leave_request=leave_req,
                    transaction_type="RELEASE",
                    amount=leave_req.total_days,
                    balance_after=balance.available,
                    description=f"Released reservation of {leave_req.total_days} days due to withdrawal",
                    created_by=user,
                )

        leave_req.status = "CANCELLED"
        leave_req.audit_log.append(
            {
                "action": "WITHDRAWN",
                "by_user_id": user.id if user else None,
                "timestamp": timezone.now().isoformat(),
            }
        )
        leave_req.save()

        leave_req.leave_days.filter(status="PENDING").update(status="CANCELLED")
        return leave_req

    @classmethod
    @transaction.atomic
    def approve_leave_request(cls, leave_req, approver_user, school):
        """
        Approves a pending leave request, transfers reserved balance to used,
        synchronizes Staff Attendance, and logs audit entries.
        """
        # Security checks
        if leave_req.school_id != school.id:
            raise PermissionDenied("Cannot approve leave for a different school.")

        if leave_req.staff.user_id and leave_req.staff.user_id == approver_user.id:
            raise PermissionDenied("Self-approval is strictly forbidden. Another authorized Principal or Trustee must approve this request.")

        if leave_req.pk:
            leave_req = LeaveRequest.objects.select_for_update().get(pk=leave_req.pk)

        if leave_req.status != "PENDING":
            raise ValidationError(f"Cannot approve request with status '{leave_req.status}'. Only PENDING requests can be approved.")

        # Find balance and lock
        leave_cycle = LeaveCycle.objects.filter(
            school=school,
            start_date__lte=leave_req.start_date,
            end_date__gte=leave_req.start_date,
        ).first() or LeaveCycle.objects.filter(school=school, is_active=True).first()

        if not leave_cycle:
            raise ValidationError("No active Leave Cycle found for this school.")

        balance = LeaveBalance.objects.select_for_update().filter(
            staff=leave_req.staff, leave_type=leave_req.leave_type, leave_cycle=leave_cycle
        ).first()

        if not balance:
            balance = cls.get_or_create_balance(leave_req.staff, leave_req.leave_type, leave_cycle)
            balance = LeaveBalance.objects.select_for_update().get(id=balance.id)

        # Deduct pending, increment used
        balance.pending = max(Decimal("0.0"), Decimal(str(balance.pending or 0)) - leave_req.total_days)
        balance.used = Decimal(str(balance.used or 0)) + leave_req.total_days
        balance.save()

        # Update LeaveRequest
        now = timezone.now()
        leave_req.status = "APPROVED"
        leave_req.approved_by = approver_user
        leave_req.approved_at = now
        leave_req.audit_log.append(
            {
                "action": "APPROVED",
                "by_user_id": approver_user.id,
                "by_user_name": str(approver_user),
                "timestamp": now.isoformat(),
            }
        )
        leave_req.save()

        # Update LeavePerDay
        leave_req.leave_days.filter(status="PENDING").update(status="APPROVED", approved_at=now)

        # Log LeaveTransaction
        LeaveTransaction.objects.create(
            school=school,
            staff=leave_req.staff,
            leave_type=leave_req.leave_type,
            leave_cycle=leave_cycle,
            leave_request=leave_req,
            transaction_type="USAGE",
            amount=leave_req.total_days,
            balance_after=balance.available,
            description=f"Approved leave #{leave_req.id} ({leave_req.total_days} days)",
            created_by=approver_user,
        )

        # Sync with Staff Attendance
        LeaveAttendanceSyncService.sync_approved_leave(leave_req)

        return leave_req

    @classmethod
    @transaction.atomic
    def reject_leave_request(cls, leave_req, approver_user, reason, school):
        """
        Rejects a pending leave request, releases reserved balance, and logs audit.
        """
        if leave_req.school_id != school.id:
            raise PermissionDenied("Cannot reject leave for a different school.")

        if leave_req.staff.user_id and leave_req.staff.user_id == approver_user.id:
            raise PermissionDenied("Self-rejection is not allowed via approver action. Use withdraw instead.")

        if leave_req.pk:
            leave_req = LeaveRequest.objects.select_for_update().get(pk=leave_req.pk)

        if leave_req.status != "PENDING":
            raise ValidationError(f"Cannot reject request with status '{leave_req.status}'. Only PENDING requests can be rejected.")

        leave_cycle = LeaveCycle.objects.filter(
            school=school,
            start_date__lte=leave_req.start_date,
            end_date__gte=leave_req.start_date,
        ).first() or LeaveCycle.objects.filter(school=school, is_active=True).first()

        if leave_cycle:
            balance = LeaveBalance.objects.select_for_update().filter(
                staff=leave_req.staff, leave_type=leave_req.leave_type, leave_cycle=leave_cycle
            ).first()
            if balance:
                balance.pending = max(Decimal("0.0"), Decimal(str(balance.pending or 0)) - leave_req.total_days)
                balance.save()

                LeaveTransaction.objects.create(
                    school=school,
                    staff=leave_req.staff,
                    leave_type=leave_req.leave_type,
                    leave_cycle=leave_cycle,
                    leave_request=leave_req,
                    transaction_type="RELEASE",
                    amount=leave_req.total_days,
                    balance_after=balance.available,
                    description=f"Released reservation due to rejection: {reason}",
                    created_by=approver_user,
                )

        leave_req.status = "REJECTED"
        leave_req.rejection_reason = reason
        leave_req.audit_log.append(
            {
                "action": "REJECTED",
                "by_user_id": approver_user.id,
                "reason": reason,
                "timestamp": timezone.now().isoformat(),
            }
        )
        leave_req.save()

        leave_req.leave_days.filter(status="PENDING").update(status="REJECTED")
        return leave_req

    @classmethod
    @transaction.atomic
    def request_cancellation(cls, leave_req, user, reason):
        """
        Staff or authorized user requests cancellation of an APPROVED leave request.
        """
        if leave_req.status != "APPROVED":
            raise ValidationError(f"Only APPROVED leave requests can be cancelled. Current status is '{leave_req.status}'.")

        if leave_req.cancellation_status in ["REQUESTED", "APPROVED"]:
            raise ValidationError(f"Cancellation is already {leave_req.cancellation_status.lower()}.")

        leave_req.cancellation_status = "REQUESTED"
        leave_req.cancellation_reason = reason
        leave_req.cancellation_requested_at = timezone.now()
        leave_req.audit_log.append(
            {
                "action": "CANCELLATION_REQUESTED",
                "by_user_id": user.id if user else None,
                "reason": reason,
                "timestamp": timezone.now().isoformat(),
            }
        )
        leave_req.save()
        return leave_req

    @classmethod
    @transaction.atomic
    def approve_cancellation(cls, leave_req, approver_user, school):
        """
        Approver approves cancellation of an approved leave request.
        Refunds used balance back to employee balance and reverts attendance.
        """
        if leave_req.school_id != school.id:
            raise PermissionDenied("Cannot action cancellation for another school.")

        if leave_req.staff.user_id and leave_req.staff.user_id == approver_user.id:
            raise PermissionDenied("Self-approval of leave cancellation is strictly forbidden.")

        if leave_req.pk:
            leave_req = LeaveRequest.objects.select_for_update().get(pk=leave_req.pk)

        if leave_req.cancellation_status != "REQUESTED":
            raise ValidationError("Leave cancellation has not been requested.")

        leave_cycle = LeaveCycle.objects.filter(
            school=school,
            start_date__lte=leave_req.start_date,
            end_date__gte=leave_req.start_date,
        ).first() or LeaveCycle.objects.filter(school=school, is_active=True).first()

        if leave_cycle:
            balance = LeaveBalance.objects.select_for_update().filter(
                staff=leave_req.staff, leave_type=leave_req.leave_type, leave_cycle=leave_cycle
            ).first()
            if balance:
                balance.used = max(Decimal("0.0"), Decimal(str(balance.used or 0)) - leave_req.total_days)
                balance.save()

                LeaveTransaction.objects.create(
                    school=school,
                    staff=leave_req.staff,
                    leave_type=leave_req.leave_type,
                    leave_cycle=leave_cycle,
                    leave_request=leave_req,
                    transaction_type="CANCELLATION",
                    amount=leave_req.total_days,
                    balance_after=balance.available,
                    description=f"Refunded {leave_req.total_days} days following cancellation approval",
                    created_by=approver_user,
                )

        now = timezone.now()
        leave_req.status = "CANCELLED"
        leave_req.cancellation_status = "APPROVED"
        leave_req.cancellation_action_by = approver_user
        leave_req.cancellation_action_at = now
        leave_req.audit_log.append(
            {
                "action": "CANCELLATION_APPROVED",
                "by_user_id": approver_user.id,
                "timestamp": now.isoformat(),
            }
        )
        leave_req.save()

        # Update per-day records
        leave_req.leave_days.filter(status="APPROVED").update(status="CANCELLED")

        # Revert Attendance
        LeaveAttendanceSyncService.revert_cancelled_leave(leave_req)

        return leave_req

    @classmethod
    @transaction.atomic
    def reject_cancellation(cls, leave_req, approver_user, reason, school):
        """
        Rejects cancellation request. Leave remains APPROVED.
        """
        if leave_req.school_id != school.id:
            raise PermissionDenied("Cannot action cancellation for another school.")

        if leave_req.pk:
            leave_req = LeaveRequest.objects.select_for_update().get(pk=leave_req.pk)

        if leave_req.cancellation_status != "REQUESTED":
            raise ValidationError("Leave cancellation has not been requested.")

        leave_req.cancellation_status = "REJECTED"
        leave_req.cancellation_rejection_reason = reason
        leave_req.cancellation_action_by = approver_user
        leave_req.cancellation_action_at = timezone.now()
        leave_req.audit_log.append(
            {
                "action": "CANCELLATION_REJECTED",
                "by_user_id": approver_user.id,
                "reason": reason,
                "timestamp": timezone.now().isoformat(),
            }
        )
        leave_req.save()
        return leave_req


class LeaveAttendanceSyncService:
    """
    Synchronizes approved leaves with the Staff Attendance module.
    Maintains punch history, avoids duplicate attendance records,
    and cleanly reverts attendance when leaves are cancelled.
    """

    @classmethod
    def sync_approved_day(cls, l_day):
        """
        Synchronizes a single approved LeavePerDay record with Attendance.
        """
        leave_req = l_day.leave
        school = l_day.school or getattr(leave_req, "school", None)
        staff = getattr(leave_req, "staff", None)
        att_date = l_day.date

        if not school or not staff or not att_date:
            return

        att, created = Attendance.objects.get_or_create(
            school=school,
            staff=staff,
            attendance_date=att_date,
            defaults={
                "name": getattr(staff, "name", ""),
                "category": getattr(staff, "category", ""),
                "is_present": False,
                "is_half_day": (l_day.day_weight == Decimal("0.5")),
                "source": "Leave",
            },
        )
        if not created:
            # If punches already exist, do NOT wipe out check_in/check_out punches!
            # Update source to indicate Leave / Half-day Leave
            if l_day.day_weight == Decimal("0.5"):
                att.is_half_day = True
            else:
                att.is_present = False
            att.source = "Leave"
            att.save()

    @classmethod
    def revert_day_attendance(cls, l_day):
        """
        Reverts Attendance record for a single LeavePerDay when rejected or cancelled.
        Preserves real punches, recalculates threshold-aware half-day state if punches exist,
        and accounts for any remaining approved leaves on the same date.
        """
        leave_req = l_day.leave
        school = l_day.school or getattr(leave_req, "school", None)
        staff = getattr(leave_req, "staff", None)
        att_date = l_day.date

        if not school or not staff or not att_date:
            return

        att = Attendance.objects.filter(school=school, staff=staff, attendance_date=att_date).first()
        if not att:
            return

        # Check if another approved leave exists on the same date (e.g., complementary half-day)
        other_approved = LeavePerDay.objects.filter(
            leave__staff=staff,
            date=att_date,
            status="APPROVED",
        ).exclude(id=l_day.id)

        if other_approved.exists():
            # Another approved leave still applies to this day
            if other_approved.filter(day_weight=Decimal("1.0")).exists():
                att.is_present = False
                att.is_half_day = False
                att.source = "Leave"
            else:
                att.is_half_day = True
                att.source = "Leave"
            att.save()
            return

        # No other approved leaves remain for this date
        if att.check_in is not None:
            # Staff had real biometric/camera punches on this day!
            att.source = "Punch"
            att.is_present = True

            punch_is_half_day = False
            try:
                policy = AttendanceSetting.objects.filter(school=school, is_active=True).first()
                if policy and policy.check_in_time and att.check_in:
                    check_in_t = att.check_in.time() if hasattr(att.check_in, "time") else att.check_in
                    c_sec = check_in_t.hour * 3600 + check_in_t.minute * 60 + check_in_t.second
                    t_sec = policy.check_in_time.hour * 3600 + policy.check_in_time.minute * 60 + policy.check_in_time.second
                    diff_mins = (c_sec - t_sec) / 60.0
                    threshold = getattr(policy, "half_day_threshold_mins", 120) or 120
                    if diff_mins > threshold:
                        punch_is_half_day = True

                if not punch_is_half_day and policy and policy.check_out_time and att.check_out:
                    check_out_t = att.check_out.time() if hasattr(att.check_out, "time") else att.check_out
                    c_sec = check_out_t.hour * 3600 + check_out_t.minute * 60 + check_out_t.second
                    t_sec = policy.check_out_time.hour * 3600 + policy.check_out_time.minute * 60 + policy.check_out_time.second
                    early_diff_mins = (t_sec - c_sec) / 60.0
                    threshold = getattr(policy, "half_day_threshold_mins", 120) or 120
                    if early_diff_mins > threshold:
                        punch_is_half_day = True
            except Exception as e:
                logger.warning("Error evaluating punch half-day threshold for staff %s on %s: %s", getattr(staff, "id", None), att_date, e)

            att.is_half_day = punch_is_half_day
            att.save()
        else:
            # Created solely by the leave request without punches.
            # Delete phantom attendance record so staff is not permanently on leave
            if att.source == "Leave":
                att.delete()

    @classmethod
    def sync_approved_leave(cls, leave_req):
        """
        For each approved leave day, updates or creates Attendance record.
        """
        for l_day in leave_req.leave_days.filter(status="APPROVED"):
            cls.sync_approved_day(l_day)

    @classmethod
    def revert_cancelled_leave(cls, leave_req):
        """
        Reverts Attendance records when leave is cancelled.
        """
        for l_day in leave_req.leave_days.filter(status="CANCELLED"):
            cls.revert_day_attendance(l_day)


class LeaveAllocationService:
    """
    Handles pro-rata allocations based on employee joining date,
    configurable cycles, and ensures idempotency.
    """

    @classmethod
    @transaction.atomic
    def allocate_leaves_for_staff(cls, staff, leave_cycle, user=None):
        """
        Allocates leaves for a single staff member for a specific cycle.
        Applies joining-date pro-rata rules.
        """
        school = staff.school
        template = staff.leave_template
        if not template or not template.is_active:
            return []

        cycle_total_days = (leave_cycle.end_date - leave_cycle.start_date).days + 1
        if cycle_total_days <= 0:
            cycle_total_days = 365

        results = []
        for lt in template.leave_types.filter(is_active=True):
            # Check if allocation already exists
            balance, created = LeaveBalance.objects.get_or_create(
                staff=staff,
                leave_type=lt,
                leave_cycle=leave_cycle,
                defaults={
                    "opening_balance": Decimal("0.0"),
                    "allocated": Decimal("0.0"),
                    "carry_forward": Decimal("0.0"),
                    "used": Decimal("0.0"),
                    "pending": Decimal("0.0"),
                },
            )

            # Prevent double allocation
            if not created and balance.allocated > Decimal("0.0"):
                continue

            base_count = Decimal(str(lt.allocation_count or 0.0))

            # Pro-rata calculation
            if lt.prorata_on_joining == "PRO_RATA" and staff.joining_date:
                if staff.joining_date > leave_cycle.end_date:
                    alloc_amount = Decimal("0.0")
                elif staff.joining_date > leave_cycle.start_date:
                    eligible_days = (leave_cycle.end_date - staff.joining_date).days + 1
                    fraction = Decimal(eligible_days) / Decimal(cycle_total_days)
                    alloc_amount = quantize_half_day(base_count * fraction)
                else:
                    alloc_amount = base_count
            elif lt.prorata_on_joining == "NONE" and staff.joining_date and staff.joining_date > leave_cycle.start_date:
                alloc_amount = Decimal("0.0")
            else:
                alloc_amount = base_count

            balance.allocated = alloc_amount
            balance.save()

            LeaveTransaction.objects.create(
                school=school,
                staff=staff,
                leave_type=lt,
                leave_cycle=leave_cycle,
                transaction_type="ALLOCATION",
                amount=alloc_amount,
                balance_after=balance.available,
                description=f"Allocated {alloc_amount} days for cycle {leave_cycle.name} (Rule: {lt.prorata_on_joining})",
                created_by=user,
            )
            results.append((lt.name or lt.leave_type, alloc_amount))

        return results

    @classmethod
    def run_bulk_allocation(cls, school, leave_cycle, user=None):
        """
        Runs allocation for all active staff members in the school.
        """
        active_staff = Staff.objects.filter(school=school, is_active=True).select_related("leave_template")
        total_allocated = 0
        for staff in active_staff:
            allocated = cls.allocate_leaves_for_staff(staff, leave_cycle, user=user)
            if allocated:
                total_allocated += len(allocated)
        return total_allocated

    @classmethod
    @transaction.atomic
    def reconcile_exit_leaves(cls, staff, leave_cycle=None, user=None):
        """
        P4 - Mid-Cycle Exit Leave Quota Deallocation (Clawback).
        Reconciles leave allocations when an employee exits mid-cycle:
        1. Checks if staff.exit_date is set. If not, returns immediately.
        2. Fetches active LeaveBalance records for the staff's current cycle.
        3. Calculates pro-rata eligible months from cycle start (or joining_date) to exit_date.
        4. Calculates the new allocated quota based on pro-rata months.
        5. Safe Clawback Rule: New allocated quota MUST NOT be less than (balance.used + balance.pending).
           If calculated pro-rata quota is lower than used + pending, sets new allocation to exactly
           (balance.used + balance.pending) so available balance becomes 0.0, preventing negative balances.
        6. Updates balance.allocated, logs an ADJUSTMENT LeaveTransaction, and saves.
        """
        if not staff.exit_date:
            return []

        school = staff.school
        if not leave_cycle:
            leave_cycle = LeaveCycle.objects.filter(
                school=school,
                is_active=True,
                is_closed=False,
                start_date__lte=staff.exit_date,
                end_date__gte=staff.exit_date,
            ).first()
            if not leave_cycle:
                leave_cycle = LeaveCycle.objects.filter(
                    school=school,
                    is_active=True,
                    is_closed=False,
                ).first()

        if not leave_cycle:
            return []

        balances = (
            LeaveBalance.objects.select_for_update()
            .filter(staff=staff, leave_cycle=leave_cycle)
            .select_related("leave_type")
        )
        if not balances.exists():
            return []

        cycle_start = leave_cycle.start_date
        cycle_end = leave_cycle.end_date

        if staff.joining_date and staff.joining_date > cycle_start:
            eff_start = staff.joining_date
        else:
            eff_start = cycle_start

        eff_end = min(staff.exit_date, cycle_end)

        total_cycle_months = (
            (cycle_end.year - cycle_start.year) * 12 + (cycle_end.month - cycle_start.month) + 1
        )
        if total_cycle_months <= 0:
            total_cycle_months = 12

        if eff_end < eff_start:
            eligible_months = Decimal("0.0")
        elif eff_start.year == eff_end.year and eff_start.month == eff_end.month:
            days_in_m = calendar.monthrange(eff_start.year, eff_start.month)[1]
            days_covered = (eff_end.day - eff_start.day) + 1
            eligible_months = Decimal(str(days_covered)) / Decimal(str(days_in_m))
        else:
            days_in_m1 = calendar.monthrange(eff_start.year, eff_start.month)[1]
            m1_fraction = Decimal(str(days_in_m1 - eff_start.day + 1)) / Decimal(str(days_in_m1))
            inter_months = (
                (eff_end.year - eff_start.year) * 12 + (eff_end.month - eff_start.month) - 1
            )
            if inter_months < 0:
                inter_months = 0
            days_in_m2 = calendar.monthrange(eff_end.year, eff_end.month)[1]
            m2_fraction = Decimal(str(eff_end.day)) / Decimal(str(days_in_m2))
            eligible_months = m1_fraction + Decimal(str(inter_months)) + m2_fraction

        results = []
        for balance in balances:
            lt = balance.leave_type
            base_count = Decimal(str(lt.allocation_count or 0.0))
            if base_count <= Decimal("0.0"):
                base_count = balance.allocated

            if total_cycle_months > 0:
                ratio = Decimal(str(eligible_months)) / Decimal(str(total_cycle_months))
                calc_quota = quantize_half_day(base_count * ratio)
            else:
                calc_quota = base_count

            # Cap at existing allocation (clawback deallocates, never increases beyond original)
            if balance.allocated > Decimal("0.0"):
                calc_quota = min(calc_quota, balance.allocated)

            # Safe Clawback Rule:
            # Must NOT be less than (balance.used + balance.pending).
            # If lower than used + pending, set to exactly (used + pending).
            committed = (balance.used or Decimal("0.0")) + (balance.pending or Decimal("0.0"))
            if calc_quota < committed:
                new_allocated = committed
            else:
                new_allocated = calc_quota

            old_allocated = balance.allocated
            balance.allocated = new_allocated
            balance.save()

            clawback = old_allocated - new_allocated
            if clawback > Decimal("0.0"):
                LeaveTransaction.objects.create(
                    school=school,
                    staff=staff,
                    leave_type=lt,
                    leave_cycle=leave_cycle,
                    transaction_type="ADJUSTMENT",
                    amount=clawback,
                    balance_after=balance.available,
                    description=(
                        f"Exit reconciliation clawback for exit date {staff.exit_date}: "
                        f"reduced allocation from {old_allocated} to {new_allocated} "
                        f"(eligible months: {eligible_months:.2f}/{total_cycle_months})"
                    ),
                    created_by=user,
                )

            results.append((lt.name or lt.leave_type, new_allocated))

        return results


class LeaveCycleClosingService:
    """
    Closes a Leave Cycle, applies Carry Forward limits,
    expires unused non-carryable leaves, and populates the next cycle's opening balance.
    Fully idempotent.
    """

    @classmethod
    @transaction.atomic
    def close_cycle(cls, closing_cycle, next_cycle, user=None):
        """
        Closes closing_cycle and rolls forward balances to next_cycle.
        """
        if closing_cycle.is_closed:
            raise ValidationError(f"Cycle '{closing_cycle.name}' is already closed.")

        if next_cycle.id == closing_cycle.id:
            raise ValidationError("Next cycle must be distinct from the closing cycle.")

        school = closing_cycle.school
        balances = LeaveBalance.objects.filter(leave_cycle=closing_cycle).select_related("staff", "leave_type")

        for bal in balances:
            lt = bal.leave_type
            unused = (bal.opening_balance + bal.allocated + bal.carry_forward) - bal.used
            unused = max(Decimal("0.0"), unused)

            cf_amount = Decimal("0.0")
            expired_amount = Decimal("0.0")

            if lt.carry_forward and unused > Decimal("0.0"):
                if lt.max_carry_forward > 0:
                    cf_limit = Decimal(str(lt.max_carry_forward))
                    cf_amount = min(unused, cf_limit)
                    expired_amount = unused - cf_amount
                else:
                    cf_amount = unused
                    expired_amount = Decimal("0.0")
            else:
                expired_amount = unused

            # Record Expiry if any
            if expired_amount > Decimal("0.0"):
                LeaveTransaction.objects.create(
                    school=school,
                    staff=bal.staff,
                    leave_type=lt,
                    leave_cycle=closing_cycle,
                    transaction_type="EXPIRY",
                    amount=expired_amount,
                    balance_after=Decimal("0.0"),
                    description=f"Expired {expired_amount} days on cycle close",
                    created_by=user,
                )

            # Credit Carry Forward to Next Cycle
            if cf_amount > Decimal("0.0"):
                next_bal, _ = LeaveBalance.objects.get_or_create(
                    staff=bal.staff,
                    leave_type=lt,
                    leave_cycle=next_cycle,
                    defaults={
                        "opening_balance": Decimal("0.0"),
                        "allocated": Decimal("0.0"),
                        "carry_forward": cf_amount,
                        "used": Decimal("0.0"),
                        "pending": Decimal("0.0"),
                    },
                )
                if not _:
                    next_bal.carry_forward = Decimal(str(next_bal.carry_forward or 0)) + cf_amount
                    next_bal.save()

                LeaveTransaction.objects.create(
                    school=school,
                    staff=bal.staff,
                    leave_type=lt,
                    leave_cycle=next_cycle,
                    transaction_type="CARRY_FORWARD",
                    amount=cf_amount,
                    balance_after=next_bal.available,
                    description=f"Carried forward {cf_amount} days from cycle {closing_cycle.name}",
                    created_by=user,
                )

        # Mark cycle closed
        closing_cycle.is_closed = True
        closing_cycle.closed_at = timezone.now()
        closing_cycle.closed_by = user
        closing_cycle.is_active = False
        closing_cycle.save()

        # Activate next cycle
        next_cycle.is_active = True
        next_cycle.save()

        return True
