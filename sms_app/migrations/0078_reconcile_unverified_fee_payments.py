from decimal import Decimal

from django.db import migrations
from django.db.models import Q, Sum
from django.utils import timezone


def reconcile_unverified_payments(apps, schema_editor):
    database = schema_editor.connection.alias
    StudentFee = apps.get_model("sms_app", "StudentFee")
    StudentFeePayment = apps.get_model("sms_app", "StudentFeePayment")

    affected_fee_ids = list(StudentFeePayment.objects.using(database).filter(
        Q(is_verified=False) | Q(is_bounced=True)
    ).values_list("student_fee_id", flat=True).distinct())

    verified_payments = StudentFeePayment.objects.using(database).filter(
        student_fee_id__in=affected_fee_ids,
        payer_type="student",
        is_verified=True,
        is_bounced=False,
    )
    totals = {
        row["student_fee_id"]: row["total"] or Decimal("0.00")
        for row in verified_payments.values("student_fee_id").annotate(total=Sum("amount"))
    }
    latest_payments = {}
    for payment in verified_payments.order_by(
        "student_fee_id", "-payment_date", "-created_at", "-pk"
    ).iterator(chunk_size=1000):
        latest_payments.setdefault(payment.student_fee_id, payment)

    fees = StudentFee.objects.using(database).filter(
        pk__in=affected_fee_ids,
        is_rte_govt_claim=False,
    ).iterator(chunk_size=500)

    for fee in fees:
        paid_amount = totals.get(fee.pk, Decimal("0.00"))
        payable_amount = max(
            Decimal("0.00"),
            (fee.amount or Decimal("0.00"))
            + (fee.fine_amount or Decimal("0.00"))
            - (fee.discount_amount or Decimal("0.00")),
        )

        if fee.status == "cancelled":
            continue
        if paid_amount <= Decimal("0.00"):
            fee.status = "pending"
            fee.paid_at = None
        elif payable_amount > Decimal("0.00") and paid_amount >= payable_amount:
            fee.status = "paid"
            latest_payment = latest_payments.get(fee.pk)
            fee.paid_at = (
                (latest_payment.payment_date or latest_payment.created_at)
                if latest_payment
                else fee.paid_at or timezone.now()
            )
        else:
            fee.status = "partial"
            fee.paid_at = None

        latest_payment = latest_payments.get(fee.pk)
        fee.paid_amount = paid_amount
        fee.payment_mode = latest_payment.payment_mode if latest_payment else None
        fee.transaction_id = latest_payment.transaction_id if latest_payment else None
        fee.save(update_fields=["paid_amount", "status", "paid_at", "payment_mode", "transaction_id"])


class Migration(migrations.Migration):
    dependencies = [("sms_app", "0077_alter_staff_department")]

    operations = [
        migrations.RunPython(reconcile_unverified_payments, migrations.RunPython.noop),
    ]
