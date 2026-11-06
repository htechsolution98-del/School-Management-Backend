from decimal import Decimal
from django.utils import timezone
import random
from typing import Dict, Any, Optional

from .models import (
    School,
    Student,
    SubscriptionPlan,
    SchoolSubscription,
    SchoolInvoice,
    SubscriptionPayment,
    SubscriptionAuditLog,
    SubscriptionSetting,
)


from dateutil.relativedelta import relativedelta


class SubscriptionBillingService:
    @classmethod
    def get_furthest_coverage_date(cls, school: Optional[School] = None, subscription: Optional[SchoolSubscription] = None):
        """
        Determines the renewal/stacking base date:
        1. If the school has an active subscription with a future due_date (due_date >= today),
           renewals stack directly on top of that due_date.
        2. If subscription is expired or overdue (due_date < today) or missing, renewal starts fresh from today.
        3. If there is no active subscription due_date set, check the most recent PAID invoice
           (ordered by paid_at / created_at desc) and use its billing_period_end if >= today.
        """
        today = timezone.now().date()
        if not school and subscription and hasattr(subscription, "school"):
            school = subscription.school
        if not subscription and school:
            subscription = getattr(school, "subscription", None)
            if not subscription:
                subscription = SchoolSubscription.objects.filter(school=school).first()

        # 1. Primary: If school has a valid active subscription due date
        if subscription and subscription.due_date:
            if subscription.due_date >= today:
                return subscription.due_date
            else:
                return today

        # 2. Fallback: If no subscription due_date, check the single most recent PAID invoice
        if school:
            latest_paid_inv = SchoolInvoice.objects.filter(
                school=school,
                status="PAID"
            ).exclude(billing_period_end__isnull=True).order_by("-paid_at", "-created_at").first()

            if latest_paid_inv and latest_paid_inv.billing_period_end:
                if latest_paid_inv.billing_period_end >= today:
                    return latest_paid_inv.billing_period_end

        return today

    @classmethod
    def calculate_renewal_period(cls, subscription: Optional[SchoolSubscription], months_count: int = 1, school: Optional[School] = None):
        """
        Calculates renewal start and end dates with stacking support:
        - If the school already has active subscription coverage (via subscription or paid invoices),
          the new subscription stacks on top of the furthest active coverage date.
        - If the subscription is expired / overdue, renewal starts from today.
        Returns: (base_date, next_due, overdue_days)
        """
        today = timezone.now().date()
        effective_months = max(1, int(months_count or 1))

        effective_school = school or (subscription.school if subscription else None)
        base_date = cls.get_furthest_coverage_date(effective_school, subscription)

        next_due = base_date + relativedelta(months=effective_months)
        overdue_days = 0

        return base_date, next_due, overdue_days

    @staticmethod
    def get_active_student_count(school: School) -> int:
        """Counts active students excluding deleted/archived/inactive ones."""
        return Student.objects.filter(school=school, is_active=True).count()

    @staticmethod
    def get_setting(key: str, default: str) -> str:
        try:
            return SubscriptionSetting.objects.get(key=key).value
        except SubscriptionSetting.DoesNotExist:
            return default

    @staticmethod
    def get_tax_percentage() -> Decimal:
        tax_enabled = SubscriptionBillingService.get_setting("TAX_ENABLED", "true").lower() == "true"
        if not tax_enabled:
            return Decimal("0.00")
        tax_pct = SubscriptionBillingService.get_setting("TAX_PERCENTAGE", "18.0")
        return Decimal(tax_pct)

    @classmethod
    def calculate_bill(
        cls,
        school: School,
        plan: Optional[SubscriptionPlan] = None,
        billing_cycle: str = "MONTHLY",
        months_count: int = 1,
        custom_student_count: Optional[int] = None,
        discount_amount: float = 0.0,
        flat_override: Optional[float] = None,
        per_student_override: Optional[float] = None,
        pricing_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculates subscription billing details with support for multi-month stacking.
        Returns:
            dict containing student_count, pricing_model, billing_cycle, months_count,
            unit_rate, subtotal, tax_percentage, tax_amount, discount_amount, final_amount,
            current_due_date, new_due_date, expanded_days, price_snapshot.
        """
        student_count = (
            custom_student_count
            if custom_student_count is not None
            else cls.get_active_student_count(school)
        )

        pricing_model = pricing_model or (plan.pricing_model if plan else "FLAT")

        # Resolve effective months count
        effective_months = max(1, int(months_count or 1))
        if billing_cycle == "QUARTERLY" and effective_months == 1:
            effective_months = 3
        elif billing_cycle == "HALF_YEARLY" and effective_months == 1:
            effective_months = 6
        elif billing_cycle == "YEARLY" and effective_months == 1:
            effective_months = 12

        # Determine base price based on cycle
        if flat_override is not None and pricing_model == "FLAT":
            unit_rate = Decimal(str(flat_override))
        elif per_student_override is not None and pricing_model == "PER_STUDENT":
            unit_rate = Decimal(str(per_student_override))
        elif plan:
            if (billing_cycle == "YEARLY" or effective_months == 12) and plan.yearly_price is not None:
                unit_rate = Decimal(str(plan.yearly_price))
            elif (billing_cycle == "HALF_YEARLY" or effective_months == 6) and plan.half_yearly_price is not None:
                unit_rate = Decimal(str(plan.half_yearly_price))
            elif (billing_cycle == "QUARTERLY" or effective_months == 3) and plan.quarterly_price is not None:
                unit_rate = Decimal(str(plan.quarterly_price))
            else:  # MONTHLY or multi-month custom
                unit_rate = Decimal(str(plan.monthly_price or 0))
        else:
            unit_rate = Decimal("0.00")

        # Multipliers / Subtotal calculation
        if pricing_model == "PER_STUDENT":
            # For per-student pricing, subtotal = student_count * per_student_rate * months
            subtotal = Decimal(str(student_count)) * unit_rate * Decimal(str(effective_months))
        else:
            # Flat pricing: if cycle matches preset (Quarterly/Half/Yearly) or months match preset, unit_rate is tier total.
            # Otherwise (e.g. 2 months, 4 months), subtotal is monthly_price * effective_months.
            if effective_months in (3, 6, 12) or billing_cycle in ("QUARTERLY", "HALF_YEARLY", "YEARLY"):
                subtotal = unit_rate
            elif billing_cycle == "MONTHLY" and effective_months > 1:
                subtotal = unit_rate * Decimal(str(effective_months))
            else:
                subtotal = unit_rate

        if unit_rate == Decimal("0.00"):
            subtotal = Decimal("0.00")

        disc = Decimal(str(discount_amount))
        net_subtotal = max(Decimal("0.00"), subtotal - disc)

        # Determine GST tax percentage from plan or global settings
        if net_subtotal == Decimal("0.00"):
            tax_pct = Decimal("0.00")
            tax_amt = Decimal("0.00")
            total_amt = Decimal("0.00")
        else:
            if plan and hasattr(plan, "gst_included"):
                tax_pct = Decimal(str(plan.gst_percentage)) if plan.gst_included else Decimal("0.00")
            else:
                tax_pct = cls.get_tax_percentage()
            tax_amt = round(net_subtotal * (tax_pct / Decimal("100.0")), 2)
            total_amt = round(net_subtotal + tax_amt, 2)

        # Calculate days expansion & future due date
        today = timezone.now().date()
        sub = getattr(school, "subscription", None)
        base_date, new_due_date, overdue_days = cls.calculate_renewal_period(sub, effective_months, school=school)
        expanded_days = max(1, (new_due_date - today).days)

        snapshot = {
            "plan_id": plan.id if plan else None,
            "plan_name": plan.name if plan else "Custom",
            "pricing_model": pricing_model,
            "billing_cycle": billing_cycle,
            "months_count": effective_months,
            "unit_rate": float(unit_rate),
            "student_count": student_count,
            "subtotal": float(subtotal),
            "gst_included": bool(plan.gst_included) if plan and hasattr(plan, "gst_included") else (tax_pct > 0),
            "tax_percentage": float(tax_pct),
            "tax_amount": float(tax_amt),
            "discount_amount": float(disc),
            "total_amount": float(total_amt),
            "current_due_date": str(base_date),
            "new_due_date": str(new_due_date),
            "expanded_days": expanded_days,
            "overdue_days": overdue_days,
            "counted_from_expiration": overdue_days > 0,
            "captured_at": timezone.now().isoformat(),
        }

        return {
            "pricing_model": pricing_model,
            "billing_cycle": billing_cycle,
            "months_count": effective_months,
            "student_count": student_count,
            "unit_rate": float(unit_rate),
            "subtotal": float(subtotal),
            "tax_percentage": float(tax_pct),
            "tax_amount": float(tax_amt),
            "discount_amount": float(disc),
            "final_amount": float(total_amt),
            "current_due_date": str(base_date),
            "new_due_date": str(new_due_date),
            "expanded_days": expanded_days,
            "overdue_days": overdue_days,
            "counted_from_expiration": overdue_days > 0,
            "price_snapshot": snapshot,
        }


class PaymentService:
    @staticmethod
    def generate_invoice_number(school: School) -> str:
        code = school.code or "SCH"
        timestamp = timezone.now().strftime("%Y%m%d")
        rnd = random.randint(100, 999)
        return f"INV-{code}-{timestamp}-{rnd}"

    @staticmethod
    def create_payment_record(
        school: School,
        subscription: SchoolSubscription,
        invoice: SchoolInvoice,
        amount: float,
        gateway: str = "RAZORPAY",
        payment_method: str = "ONLINE",
        transaction_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> SubscriptionPayment:
        rnd = random.randint(1000, 9999)
        pid = f"PAY-{timezone.now().strftime('%Y%m%d%H%M%S')}-{rnd}"
        payment = SubscriptionPayment.objects.create(
            payment_id=pid,
            school=school,
            subscription=subscription,
            invoice=invoice,
            transaction_id=transaction_id or pid,
            gateway=gateway,
            amount=Decimal(str(amount)),
            currency="INR",
            status="INITIATED",
            payment_method=payment_method,
            metadata=metadata or {},
        )
        return payment


class AuditLogService:
    @staticmethod
    def log(
        action: str,
        school: Optional[School] = None,
        user: Optional[Any] = None,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> SubscriptionAuditLog:
        return SubscriptionAuditLog.objects.create(
            school=school,
            user=user if (user and user.is_authenticated) else None,
            action=action,
            old_values=old_values or {},
            new_values=new_values or {},
            notes=notes,
        )
