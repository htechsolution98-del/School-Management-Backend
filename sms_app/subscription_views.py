from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
import random

from .models import School, SchoolSubscription, SchoolInvoice, Student
from .subscription_serializers import (
    SchoolSubscriptionSerializer,
    SchoolInvoiceSerializer,
)
from .permissions import Is_super_admin


class SchoolSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = SchoolSubscription.objects.select_related("school").all()
    serializer_class = SchoolSubscriptionSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    def get_queryset(self):
        # Auto-ensure every school has a subscription record
        schools_without_sub = School.objects.filter(subscription__isnull=True)
        today = timezone.now().date()
        for sch in schools_without_sub:
            SchoolSubscription.objects.create(
                school=sch,
                plan_type="TRIAL",
                billing_model="FLAT",
                billing_cycle="MONTHLY",
                flat_amount=5000.00,
                per_student_rate=15.00,
                start_date=today,
                due_date=today + timedelta(days=30),
                status="TRIAL",
            )

        # Refresh overdue statuses
        subs = SchoolSubscription.objects.select_related("school").all()
        for sub in subs:
            if sub.status in ["TRIAL", "ACTIVE"] and sub.due_date < today:
                sub.status = "EXPIRED"
                sub.save(update_fields=["status"])
                # If auto-lock is on, deactivate school
                if sub.auto_lock_on_due and sub.school.is_active:
                    sub.school.is_active = False
                    sub.school.save(update_fields=["is_active"])

        return SchoolSubscription.objects.select_related("school").order_by("school__name")

    @action(detail=False, methods=["get"], url_path="summary")
    def get_summary(self, request):
        today = timezone.now().date()
        subs = self.get_queryset()

        total_schools = subs.count()
        active_paid = subs.filter(status="ACTIVE").count()
        active_trials = subs.filter(status="TRIAL").count()
        expired_overdue = subs.filter(status__in=["EXPIRED", "SUSPENDED"]).count()

        # Calculate projected Monthly Recurring Revenue (MRR)
        projected_mrr = 0.0
        for sub in subs.filter(status__in=["ACTIVE", "TRIAL"]):
            amt = sub.calculate_current_amount()
            if sub.billing_cycle == "QUARTERLY":
                projected_mrr += (amt / 3.0)
            elif sub.billing_cycle == "YEARLY":
                projected_mrr += (amt / 12.0)
            else:
                projected_mrr += amt

        return Response({
            "total_schools": total_schools,
            "active_paid": active_paid,
            "active_trials": active_trials,
            "expired_overdue": expired_overdue,
            "projected_monthly_revenue": round(projected_mrr, 2),
        })

    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(self, request, pk=None):
        subscription = self.get_object()
        data = request.data

        amount = float(data.get("amount") or subscription.calculate_current_amount())
        payment_method = data.get("payment_method", "ONLINE")
        payment_reference = data.get("payment_reference", "")
        notes = data.get("notes", "")

        today = timezone.now().date()

        # Determine next due date based on cycle
        cycle = data.get("billing_cycle", subscription.billing_cycle)
        custom_next_due = data.get("next_due_date")

        if custom_next_due:
            from datetime import datetime
            next_due = datetime.strptime(custom_next_due, "%Y-%m-%d").date()
        else:
            base_date = max(today, subscription.due_date)
            if cycle == "QUARTERLY":
                next_due = base_date + relativedelta(months=3)
            elif cycle == "YEARLY":
                next_due = base_date + relativedelta(years=1)
            else:  # MONTHLY
                next_due = base_date + relativedelta(months=1)

        with transaction.atomic():
            # 1. Update subscription status
            subscription.plan_type = "PAID"
            subscription.status = "ACTIVE"
            subscription.start_date = today
            subscription.due_date = next_due
            subscription.billing_cycle = cycle
            if "flat_amount" in data:
                subscription.flat_amount = data["flat_amount"]
            if "per_student_rate" in data:
                subscription.per_student_rate = data["per_student_rate"]
            if "billing_model" in data:
                subscription.billing_model = data["billing_model"]
            subscription.save()

            # 2. Reactivate school
            subscription.school.is_active = True
            subscription.school.save(update_fields=["is_active"])

            # 3. Create paid invoice record
            student_count = subscription.get_live_student_count()
            unit_rate = (
                subscription.per_student_rate
                if subscription.billing_model == "PER_STUDENT"
                else subscription.flat_amount
            )

            inv_no = f"INV-{subscription.school.code or 'SCH'}-{timezone.now().strftime('%Y%m')}-{random.randint(100, 999)}"

            invoice = SchoolInvoice.objects.create(
                school=subscription.school,
                subscription=subscription,
                invoice_number=inv_no,
                billing_model=subscription.billing_model,
                student_count=student_count,
                unit_rate=unit_rate,
                subtotal=amount,
                tax_amount=0.00,
                total_amount=amount,
                billing_period_start=today,
                billing_period_end=next_due,
                due_date=today,
                status="PAID",
                paid_at=timezone.now(),
                payment_method=payment_method,
                payment_reference=payment_reference,
                notes=notes,
            )

        return Response({
            "message": "Payment recorded successfully and school subscription renewed!",
            "subscription": SchoolSubscriptionSerializer(subscription).data,
            "invoice": SchoolInvoiceSerializer(invoice).data,
        })

    @action(detail=True, methods=["post"], url_path="generate-invoice")
    def generate_invoice(self, request, pk=None):
        subscription = self.get_object()
        today = timezone.now().date()
        student_count = subscription.get_live_student_count()
        amount = subscription.calculate_current_amount()
        unit_rate = (
            subscription.per_student_rate
            if subscription.billing_model == "PER_STUDENT"
            else subscription.flat_amount
        )

        inv_no = f"INV-{subscription.school.code or 'SCH'}-{timezone.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"

        invoice = SchoolInvoice.objects.create(
            school=subscription.school,
            subscription=subscription,
            invoice_number=inv_no,
            billing_model=subscription.billing_model,
            student_count=student_count,
            unit_rate=unit_rate,
            subtotal=amount,
            tax_amount=0.00,
            total_amount=amount,
            billing_period_start=today,
            billing_period_end=subscription.due_date,
            due_date=subscription.due_date,
            status="PENDING",
            notes=f"Auto-generated invoice based on {subscription.billing_model} billing model.",
        )

        return Response({
            "message": "Invoice generated successfully!",
            "invoice": SchoolInvoiceSerializer(invoice).data,
        })

    @action(detail=True, methods=["post"], url_path="toggle-lock")
    def toggle_lock(self, request, pk=None):
        subscription = self.get_object()
        school = subscription.school

        if school.is_active:
            school.is_active = False
            subscription.status = "SUSPENDED"
            msg = "School locked/suspended successfully."
        else:
            school.is_active = True
            subscription.status = "ACTIVE" if subscription.plan_type == "PAID" else "TRIAL"
            msg = "School unlocked/activated successfully."

        school.save(update_fields=["is_active"])
        subscription.save(update_fields=["status"])

        return Response({
            "message": msg,
            "subscription": SchoolSubscriptionSerializer(subscription).data,
        })


class SchoolInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SchoolInvoice.objects.select_related("school", "subscription").all()
    serializer_class = SchoolInvoiceSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    def get_queryset(self):
        qs = super().get_queryset()
        school_id = self.request.query_params.get("school")
        if school_id:
            qs = qs.filter(school_id=school_id)
        return qs.order_by("-created_at")

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        invoice = self.get_object()
        data = request.data
        invoice.status = "PAID"
        invoice.paid_at = timezone.now()
        invoice.payment_method = data.get("payment_method", invoice.payment_method)
        invoice.payment_reference = data.get("payment_reference", invoice.payment_reference)
        invoice.save()

        return Response({
            "message": "Invoice marked as paid successfully.",
            "invoice": SchoolInvoiceSerializer(invoice).data,
        })
