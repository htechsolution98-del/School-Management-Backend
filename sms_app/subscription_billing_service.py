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


class SubscriptionBillingService:
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
        custom_student_count: Optional[int] = None,
        discount_amount: float = 0.0,
        flat_override: Optional[float] = None,
        per_student_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calculates subscription billing details.
        Returns:
            dict containing student_count, pricing_model, billing_cycle, unit_rate,
            subtotal, tax_percentage, tax_amount, discount_amount, final_amount, price_snapshot.
        """
        student_count = (
            custom_student_count
            if custom_student_count is not None
            else cls.get_active_student_count(school)
        )

        pricing_model = plan.pricing_model if plan else "FLAT"

        # Determine base price based on cycle
        if flat_override is not None and pricing_model == "FLAT":
            unit_rate = Decimal(str(flat_override))
        elif per_student_override is not None and pricing_model == "PER_STUDENT":
            unit_rate = Decimal(str(per_student_override))
        elif plan:
            if billing_cycle == "QUARTERLY":
                unit_rate = plan.quarterly_price
            elif billing_cycle == "HALF_YEARLY":
                unit_rate = plan.half_yearly_price
            elif billing_cycle == "YEARLY":
                unit_rate = plan.yearly_price
            else:  # MONTHLY
                unit_rate = plan.monthly_price
        else:
            unit_rate = Decimal("0.00")

        # Multipliers / Subtotal calculation
        if pricing_model == "PER_STUDENT":
            # For per-student pricing, subtotal = student_count * per_student_rate * cycle_months
            cycle_months = 1
            if billing_cycle == "QUARTERLY":
                cycle_months = 3
            elif billing_cycle == "HALF_YEARLY":
                cycle_months = 6
            elif billing_cycle == "YEARLY":
                cycle_months = 12

            subtotal = Decimal(str(student_count)) * unit_rate * Decimal(str(cycle_months))
        else:
            # Flat pricing is per cycle directly
            subtotal = unit_rate

        disc = Decimal(str(discount_amount))
        net_subtotal = max(Decimal("0.00"), subtotal - disc)

        tax_pct = cls.get_tax_percentage()
        tax_amt = round(net_subtotal * (tax_pct / Decimal("100.0")), 2)
        total_amt = round(net_subtotal + tax_amt, 2)

        snapshot = {
            "plan_id": plan.id if plan else None,
            "plan_name": plan.name if plan else "Custom",
            "pricing_model": pricing_model,
            "billing_cycle": billing_cycle,
            "unit_rate": float(unit_rate),
            "student_count": student_count,
            "subtotal": float(subtotal),
            "tax_percentage": float(tax_pct),
            "tax_amount": float(tax_amt),
            "discount_amount": float(disc),
            "total_amount": float(total_amt),
            "captured_at": timezone.now().isoformat(),
        }

        return {
            "pricing_model": pricing_model,
            "billing_cycle": billing_cycle,
            "student_count": student_count,
            "unit_rate": float(unit_rate),
            "subtotal": float(subtotal),
            "tax_percentage": float(tax_pct),
            "tax_amount": float(tax_amt),
            "discount_amount": float(disc),
            "final_amount": float(total_amt),
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
