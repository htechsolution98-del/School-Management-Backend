from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.db import transaction
from decimal import Decimal
import random

from .models import (
    School,
    Module,
    SubscriptionPlan,
    SubscriptionPlanModule,
    SchoolSubscription,
    SchoolInvoice,
    SubscriptionPayment,
    SubscriptionAuditLog,
    SubscriptionSetting,
)
from .subscription_serializers import (
    SubscriptionPlanSerializer,
    SubscriptionPlanModuleSerializer,
    SchoolSubscriptionSerializer,
    SchoolInvoiceSerializer,
    SubscriptionPaymentSerializer,
    SubscriptionAuditLogSerializer,
    SubscriptionSettingSerializer,
)
from .subscription_services import (
    SubscriptionBillingService,
    PaymentService,
    AuditLogService,
)
from django.conf import settings
from .permissions import Is_super_admin
from .razorpay_client import client as razorpay_client
import hmac
import hashlib



class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.prefetch_related("plan_modules__module").all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    @action(detail=False, methods=["get"], url_path="public", permission_classes=[IsAuthenticated])
    def public_plans(self, request):
        """Exposes active plans for school subscription selection."""
        plans = SubscriptionPlan.objects.filter(is_active=True).prefetch_related("plan_modules__module")
        serializer = SubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)


class SchoolSubscriptionViewSet(viewsets.ModelViewSet):
    queryset = SchoolSubscription.objects.select_related("school", "plan").all()
    serializer_class = SchoolSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action in ["list", "retrieve", "extend_trial", "manual_subscription", "toggle_lock", "get_summary"]:
            return [IsAuthenticated(), Is_super_admin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        # Auto-ensure every school has a subscription record
        schools_without_sub = School.objects.filter(subscription__isnull=True)
        today = timezone.now().date()
        default_trial_days = int(SubscriptionBillingService.get_setting("DEFAULT_TRIAL_DAYS", "14"))

        for sch in schools_without_sub:
            SchoolSubscription.objects.create(
                school=sch,
                plan_type="TRIAL",
                billing_model="FLAT",
                billing_cycle="MONTHLY",
                flat_amount=Decimal("5000.00"),
                per_student_rate=Decimal("15.00"),
                trial_start_date=today,
                trial_end_date=today + timedelta(days=default_trial_days),
                start_date=today,
                due_date=today + timedelta(days=default_trial_days),
                grace_period_days=int(SubscriptionBillingService.get_setting("DEFAULT_GRACE_PERIOD_DAYS", "7")),
                status="TRIAL",
            )

        # Refresh overdue statuses
        subs = SchoolSubscription.objects.select_related("school", "plan").all()
        for sub in subs:
            if sub.status in ["TRIAL", "ACTIVE", "EXPIRING"] and sub.due_date < today:
                grace_days = sub.grace_period_days
                if today <= (sub.due_date + timedelta(days=grace_days)):
                    if sub.status != "GRACE_PERIOD":
                        sub.status = "GRACE_PERIOD"
                        sub.save(update_fields=["status"])
                else:
                    new_status = "TRIAL_EXPIRED" if sub.plan_type == "TRIAL" else "EXPIRED"
                    if sub.auto_lock_on_due:
                        new_status = "SUSPENDED"
                        if sub.school.is_active:
                            sub.school.is_active = False
                            sub.school.save(update_fields=["is_active"])
                    sub.status = new_status
                    sub.save(update_fields=["status"])

        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            return SchoolSubscription.objects.select_related("school", "plan").order_by("school__name")

        if getattr(user, "school", None):
            return SchoolSubscription.objects.filter(school=user.school).select_related("school", "plan")

        return SchoolSubscription.objects.none()

    @action(detail=False, methods=["get"], url_path="current")
    def get_current(self, request):
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "User is not associated with any school."}, status=400)

        sub, _ = SchoolSubscription.objects.get_or_create(
            school=school,
            defaults={
                "plan_type": "TRIAL",
                "billing_model": "FLAT",
                "billing_cycle": "MONTHLY",
                "flat_amount": Decimal("5000.00"),
                "per_student_rate": Decimal("15.00"),
                "trial_start_date": timezone.now().date(),
                "trial_end_date": timezone.now().date() + timedelta(days=14),
                "start_date": timezone.now().date(),
                "due_date": timezone.now().date() + timedelta(days=14),
                "grace_period_days": 7,
                "status": "TRIAL",
            },
        )
        serializer = SchoolSubscriptionSerializer(sub)

        # Build module permissions list
        if sub.plan:
            modules = SubscriptionPlanModule.objects.filter(plan=sub.plan, is_enabled=True).values_list("module__code", flat=True)
        else:
            modules = Module.objects.filter(is_active=True).values_list("code", flat=True)

        return Response({
            "subscription": serializer.data,
            "enabled_modules": list(modules),
            "live_student_count": sub.get_live_student_count(),
        })

    @action(detail=False, methods=["get"], url_path="summary")
    def get_summary(self, request):
        today = timezone.now().date()
        subs = self.get_queryset()

        total_schools = subs.count()
        active_paid = subs.filter(status="ACTIVE").count()
        active_trials = subs.filter(status="TRIAL").count()
        expiring_soon = subs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7)).count()
        expired_overdue = subs.filter(status__in=["EXPIRED", "TRIAL_EXPIRED", "SUSPENDED"]).count()

        # Calculate projected Monthly Recurring Revenue (MRR)
        projected_mrr = 0.0
        for sub in subs.filter(status__in=["ACTIVE", "TRIAL"]):
            amt = sub.calculate_current_amount()
            if sub.billing_cycle == "QUARTERLY":
                projected_mrr += (amt / 3.0)
            elif sub.billing_cycle == "HALF_YEARLY":
                projected_mrr += (amt / 6.0)
            elif sub.billing_cycle == "YEARLY":
                projected_mrr += (amt / 12.0)
            else:
                projected_mrr += amt

        return Response({
            "total_schools": total_schools,
            "active_paid": active_paid,
            "active_trials": active_trials,
            "expiring_soon": expiring_soon,
            "expired_overdue": expired_overdue,
            "projected_monthly_revenue": round(projected_mrr, 2),
            "projected_annual_revenue": round(projected_mrr * 12.0, 2),
        })

    @action(detail=False, methods=["post"], url_path="checkout-calculate")
    def checkout_calculate(self, request):
        """Calculates billing breakdown before purchasing/renewing."""
        data = request.data
        user = request.user
        school_id = data.get("school_id")

        if getattr(user, "is_superuser", False) and school_id:
            try:
                school = School.objects.get(id=school_id)
            except School.DoesNotExist:
                return Response({"error": "School not found."}, status=404)
        else:
            school = getattr(user, "school", None)

        if not school:
            return Response({"error": "No valid school found."}, status=400)

        plan_id = data.get("plan_id")
        plan = None
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                return Response({"error": "Plan not found."}, status=404)

        billing_cycle = data.get("billing_cycle", "MONTHLY")
        custom_students = data.get("custom_student_count")
        discount = float(data.get("discount_amount", 0.0))

        calculation = SubscriptionBillingService.calculate_bill(
            school=school,
            plan=plan,
            billing_cycle=billing_cycle,
            custom_student_count=custom_students,
            discount_amount=discount,
        )
        return Response(calculation)

    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(self, request, pk=None):
        subscription = self.get_object()
        data = request.data

        plan_id = data.get("plan_id")
        plan = None
        if plan_id:
            try:
                plan = SubscriptionPlan.objects.get(id=plan_id)
            except SubscriptionPlan.DoesNotExist:
                pass

        billing_cycle = data.get("billing_cycle", subscription.billing_cycle)
        payment_method = data.get("payment_method", "ONLINE")
        payment_reference = data.get("payment_reference", "")
        notes = data.get("notes", "")

        today = timezone.now().date()
        custom_next_due = data.get("next_due_date")

        if custom_next_due:
            from datetime import datetime
            next_due = datetime.strptime(custom_next_due, "%Y-%m-%d").date()
        else:
            base_date = max(today, subscription.due_date)
            if billing_cycle == "QUARTERLY":
                next_due = base_date + relativedelta(months=3)
            elif billing_cycle == "HALF_YEARLY":
                next_due = base_date + relativedelta(months=6)
            elif billing_cycle == "YEARLY":
                next_due = base_date + relativedelta(years=1)
            else:
                next_due = base_date + relativedelta(months=1)

        bill_calc = SubscriptionBillingService.calculate_bill(
            school=subscription.school,
            plan=plan or subscription.plan,
            billing_cycle=billing_cycle,
            discount_amount=float(data.get("discount_amount", 0.0)),
        )

        amount = float(data.get("amount") or bill_calc["final_amount"])

        old_vals = {
            "status": subscription.status,
            "due_date": str(subscription.due_date),
            "plan_type": subscription.plan_type,
        }

        with transaction.atomic():
            # 1. Update subscription status & snapshot
            if plan:
                subscription.plan = plan
                subscription.billing_model = plan.pricing_model

            subscription.plan_type = "PAID"
            subscription.status = "ACTIVE"
            subscription.subscription_start_date = today
            subscription.subscription_end_date = next_due
            subscription.start_date = today
            subscription.due_date = next_due
            subscription.billing_cycle = billing_cycle
            subscription.student_count_at_purchase = bill_calc["student_count"]
            subscription.price_snapshot = bill_calc["price_snapshot"]
            subscription.flat_amount = Decimal(str(bill_calc["unit_rate"])) if subscription.billing_model == "FLAT" else Decimal("0.00")
            subscription.per_student_rate = Decimal(str(bill_calc["unit_rate"])) if subscription.billing_model == "PER_STUDENT" else Decimal("0.00")
            subscription.save()

            # 2. Reactivate school
            subscription.school.is_active = True
            subscription.school.save(update_fields=["is_active"])

            # 3. Create paid invoice record
            inv_no = PaymentService.generate_invoice_number(subscription.school)

            invoice = SchoolInvoice.objects.create(
                school=subscription.school,
                subscription=subscription,
                invoice_number=inv_no,
                billing_model=subscription.billing_model,
                billing_cycle=billing_cycle,
                student_count=bill_calc["student_count"],
                unit_rate=Decimal(str(bill_calc["unit_rate"])),
                subtotal=Decimal(str(bill_calc["subtotal"])),
                tax_percentage=Decimal(str(bill_calc["tax_percentage"])),
                tax_amount=Decimal(str(bill_calc["tax_amount"])),
                discount_amount=Decimal(str(bill_calc["discount_amount"])),
                total_amount=Decimal(str(amount)),
                billing_period_start=today,
                billing_period_end=next_due,
                due_date=today,
                status="PAID",
                paid_at=timezone.now(),
                payment_method=payment_method,
                payment_reference=payment_reference,
                notes=notes,
            )

            # 4. Create payment log
            payment = PaymentService.create_payment_record(
                school=subscription.school,
                subscription=subscription,
                invoice=invoice,
                amount=amount,
                gateway="MANUAL" if payment_method != "ONLINE" else "RAZORPAY",
                payment_method=payment_method,
                transaction_id=payment_reference,
            )
            payment.status = "SUCCESS"
            payment.paid_at = timezone.now()
            payment.save()

            # 5. Log audit entry
            AuditLogService.log(
                action="SUBSCRIPTION_RENEWED",
                school=subscription.school,
                user=request.user,
                old_values=old_vals,
                new_values={
                    "status": "ACTIVE",
                    "due_date": str(next_due),
                    "amount": amount,
                    "invoice": inv_no,
                },
                notes=f"Payment of ₹{amount} recorded via {payment_method}.",
            )

        return Response({
            "message": "Payment recorded successfully and subscription activated!",
            "subscription": SchoolSubscriptionSerializer(subscription).data,
            "invoice": SchoolInvoiceSerializer(invoice).data,
            "payment": SubscriptionPaymentSerializer(payment).data,
        })

    @action(detail=True, methods=["post"], url_path="extend-trial")
    def extend_trial(self, request, pk=None):
        subscription = self.get_object()
        additional_days = int(request.data.get("days", 7))
        old_due = subscription.due_date

        subscription.due_date = old_due + timedelta(days=additional_days)
        if subscription.trial_end_date:
            subscription.trial_end_date = subscription.trial_end_date + timedelta(days=additional_days)
        subscription.status = "TRIAL"
        subscription.save()

        # Ensure school is active
        subscription.school.is_active = True
        subscription.school.save(update_fields=["is_active"])

        AuditLogService.log(
            action="TRIAL_EXTENDED",
            school=subscription.school,
            user=request.user,
            old_values={"due_date": str(old_due), "status": subscription.status},
            new_values={"due_date": str(subscription.due_date), "added_days": additional_days},
            notes=request.data.get("notes", f"Trial extended by {additional_days} days."),
        )

        return Response({
            "message": f"Trial extended by {additional_days} days until {subscription.due_date}.",
            "subscription": SchoolSubscriptionSerializer(subscription).data,
        })

    @action(detail=False, methods=["post"], url_path="manual-subscription")
    def manual_subscription(self, request):
        """Allows Super Admin to manually create/activate a subscription for a school (offline/bank transfer)."""
        data = request.data
        school_id = data.get("school_id")
        try:
            school = School.objects.get(id=school_id)
        except School.DoesNotExist:
            return Response({"error": "School not found."}, status=404)

        plan_id = data.get("plan_id")
        plan = SubscriptionPlan.objects.filter(id=plan_id).first() if plan_id else None

        billing_cycle = data.get("billing_cycle", "MONTHLY")
        start_date_str = data.get("start_date")
        due_date_str = data.get("due_date")
        amount = float(data.get("amount", 0.0))
        ref_no = data.get("payment_reference", "OFFLINE_MANUAL")
        notes = data.get("notes", "Manually activated by Super Admin")

        from datetime import datetime
        today = timezone.now().date()
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date() if start_date_str else today

        if due_date_str:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
        else:
            if billing_cycle == "QUARTERLY":
                due_date = start_date + relativedelta(months=3)
            elif billing_cycle == "HALF_YEARLY":
                due_date = start_date + relativedelta(months=6)
            elif billing_cycle == "YEARLY":
                due_date = start_date + relativedelta(years=1)
            else:
                due_date = start_date + relativedelta(months=1)

        sub, _ = SchoolSubscription.objects.get_or_create(school=school, defaults={"due_date": due_date})

        with transaction.atomic():
            sub.plan = plan
            sub.plan_type = "PAID"
            sub.status = "ACTIVE"
            sub.billing_cycle = billing_cycle
            sub.billing_model = plan.pricing_model if plan else data.get("billing_model", "FLAT")
            sub.start_date = start_date
            sub.due_date = due_date
            sub.subscription_start_date = start_date
            sub.subscription_end_date = due_date
            sub.notes = notes
            sub.save()

            school.is_active = True
            school.save(update_fields=["is_active"])

            inv_no = PaymentService.generate_invoice_number(school)
            invoice = SchoolInvoice.objects.create(
                school=school,
                subscription=sub,
                invoice_number=inv_no,
                billing_model=sub.billing_model,
                billing_cycle=billing_cycle,
                student_count=sub.get_live_student_count(),
                subtotal=Decimal(str(amount)),
                total_amount=Decimal(str(amount)),
                billing_period_start=start_date,
                billing_period_end=due_date,
                due_date=today,
                status="PAID",
                paid_at=timezone.now(),
                payment_method=data.get("payment_method", "BANK_TRANSFER"),
                payment_reference=ref_no,
                notes=notes,
            )

            AuditLogService.log(
                action="MANUAL_SUBSCRIPTION_CREATED",
                school=school,
                user=request.user,
                new_values={"plan": plan.name if plan else "Custom", "amount": amount, "due_date": str(due_date)},
                notes=notes,
            )

        return Response({
            "message": "Manual subscription created and activated successfully!",
            "subscription": SchoolSubscriptionSerializer(sub).data,
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

        AuditLogService.log(
            action="TOGGLE_LOCK",
            school=school,
            user=request.user,
            new_values={"is_active": school.is_active, "status": subscription.status},
        )

        return Response({
            "message": msg,
            "subscription": SchoolSubscriptionSerializer(subscription).data,
        })


class SchoolInvoiceViewSet(viewsets.ModelViewSet):
    queryset = SchoolInvoice.objects.select_related("school", "subscription").all()
    serializer_class = SchoolInvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            school_id = self.request.query_params.get("school")
            if school_id:
                qs = qs.filter(school_id=school_id)
            return qs.order_by("-created_at")

        if getattr(user, "school", None):
            return qs.filter(school=user.school).order_by("-created_at")

        return SchoolInvoice.objects.none()

    @action(detail=True, methods=["post"], url_path="mark-paid")
    def mark_paid(self, request, pk=None):
        if not (request.user.is_superuser or request.user.role in ["superadmin", "super_admin"]):
            return Response({"error": "Only superadmin can mark invoice paid manually."}, status=403)

        invoice = self.get_object()
        data = request.data
        invoice.status = "PAID"
        invoice.paid_at = timezone.now()
        invoice.payment_method = data.get("payment_method", invoice.payment_method)
        invoice.payment_reference = data.get("payment_reference", invoice.payment_reference)
        invoice.save()

        AuditLogService.log(
            action="INVOICE_MARKED_PAID",
            school=invoice.school,
            user=request.user,
            new_values={"invoice_number": invoice.invoice_number, "amount": float(invoice.total_amount)},
        )

        return Response({
            "message": "Invoice marked as paid successfully.",
            "invoice": SchoolInvoiceSerializer(invoice).data,
        })


class SubscriptionPaymentViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPayment.objects.select_related("school", "subscription", "invoice").all()
    serializer_class = SubscriptionPaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_superuser", False) or getattr(user, "role", "") in ["superadmin", "super_admin"]:
            return SubscriptionPayment.objects.select_related("school", "subscription", "invoice").order_by("-created_at")
        if getattr(user, "school", None):
            return SubscriptionPayment.objects.filter(school=user.school).select_related("school", "subscription", "invoice").order_by("-created_at")
        return SubscriptionPayment.objects.none()

    @action(detail=False, methods=["post"], url_path="create-razorpay-order")
    def create_razorpay_order(self, request):
        user = request.user
        school = getattr(user, "school", None)
        if not school:
            return Response({"error": "No school associated with user."}, status=400)

        sub = getattr(school, "subscription", None)
        if not sub:
            return Response({"error": "No subscription found for school."}, status=404)

        data = request.data
        plan_id = data.get("plan_id")
        plan = SubscriptionPlan.objects.filter(id=plan_id).first() if plan_id else sub.plan
        billing_cycle = data.get("billing_cycle", sub.billing_cycle)

        calc = SubscriptionBillingService.calculate_bill(school=school, plan=plan, billing_cycle=billing_cycle)
        amount_paisa = int(calc["final_amount"] * 100)

        order_data = {
            "amount": amount_paisa,
            "currency": "INR",
            "receipt": f"receipt_{school.id}_{int(timezone.now().timestamp())}",
            "payment_capture": 1,
        }

        try:
            order = razorpay_client.order.create(data=order_data)
        except Exception as e:
            return Response({"error": f"Failed to create Razorpay order: {str(e)}"}, status=500)

        # Store pending payment record
        inv_no = PaymentService.generate_invoice_number(school)
        invoice = SchoolInvoice.objects.create(
            school=school,
            subscription=sub,
            invoice_number=inv_no,
            billing_model=calc["pricing_model"],
            billing_cycle=billing_cycle,
            student_count=calc["student_count"],
            unit_rate=Decimal(str(calc["unit_rate"])),
            subtotal=Decimal(str(calc["subtotal"])),
            tax_percentage=Decimal(str(calc["tax_percentage"])),
            tax_amount=Decimal(str(calc["tax_amount"])),
            discount_amount=Decimal(str(calc["discount_amount"])),
            total_amount=Decimal(str(calc["final_amount"])),
            billing_period_start=timezone.now().date(),
            billing_period_end=timezone.now().date() + timedelta(days=30),
            due_date=timezone.now().date(),
            status="PENDING",
        )

        payment = PaymentService.create_payment_record(
            school=school,
            subscription=sub,
            invoice=invoice,
            amount=calc["final_amount"],
            gateway="RAZORPAY",
            transaction_id=order["id"],
            metadata={"razorpay_order_id": order["id"], "plan_id": plan.id if plan else None, "billing_cycle": billing_cycle},
        )

        return Response({
            "order_id": order["id"],
            "amount": calc["final_amount"],
            "currency": "INR",
            "key": getattr(razorpay_client, "auth", [""])[0],
            "payment_id": payment.payment_id,
            "invoice_number": inv_no,
        })

    @action(detail=False, methods=["post"], url_path="verify-razorpay-payment")
    def verify_razorpay_payment(self, request):
        data = request.data
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")

        if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
            return Response({"error": "Missing Razorpay payment parameters."}, status=400)

        # Signature verification
        body = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        secret_key = getattr(settings, "RAZOR_PAY_SECRET_KEY", "dummy_secret")
        generated_signature = hmac.new(
            secret_key.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()


        if generated_signature != razorpay_signature:
            return Response({"error": "Invalid payment signature."}, status=400)

        payment = SubscriptionPayment.objects.filter(transaction_id=razorpay_order_id).first()
        if not payment:
            return Response({"error": "Payment record not found."}, status=404)

        with transaction.atomic():
            payment.status = "SUCCESS"
            payment.paid_at = timezone.now()
            payment.transaction_id = razorpay_payment_id
            payment.save()

            if payment.invoice:
                payment.invoice.status = "PAID"
                payment.invoice.paid_at = timezone.now()
                payment.invoice.payment_reference = razorpay_payment_id
                payment.invoice.save()

            # Activate subscription
            sub = payment.subscription
            if sub:
                plan_id = payment.metadata.get("plan_id")
                plan = SubscriptionPlan.objects.filter(id=plan_id).first() if plan_id else sub.plan
                billing_cycle = payment.metadata.get("billing_cycle", sub.billing_cycle)

                today = timezone.now().date()
                if billing_cycle == "QUARTERLY":
                    next_due = today + relativedelta(months=3)
                elif billing_cycle == "HALF_YEARLY":
                    next_due = today + relativedelta(months=6)
                elif billing_cycle == "YEARLY":
                    next_due = today + relativedelta(years=1)
                else:
                    next_due = today + relativedelta(months=1)

                sub.plan = plan
                sub.plan_type = "PAID"
                sub.status = "ACTIVE"
                sub.billing_cycle = billing_cycle
                sub.start_date = today
                sub.due_date = next_due
                sub.subscription_start_date = today
                sub.subscription_end_date = next_due
                sub.save()

                sub.school.is_active = True
                sub.school.save(update_fields=["is_active"])

                AuditLogService.log(
                    action="PAYMENT_VERIFIED",
                    school=sub.school,
                    user=request.user,
                    new_values={"payment_id": payment.payment_id, "amount": float(payment.amount), "gateway": "RAZORPAY"},
                    notes="Razorpay online payment verified successfully.",
                )

        return Response({"message": "Payment verified and subscription activated successfully!"})


class SubscriptionAuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionAuditLog.objects.select_related("school", "user").all()
    serializer_class = SubscriptionAuditLogSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]


class SubscriptionSettingViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionSetting.objects.all()
    serializer_class = SubscriptionSettingSerializer
    permission_classes = [IsAuthenticated, Is_super_admin]

    @action(detail=False, methods=["get"], url_path="all")
    def get_all_settings(self, request):
        defaults = {
            "DEFAULT_TRIAL_DAYS": "14",
            "DEFAULT_GRACE_PERIOD_DAYS": "7",
            "TAX_ENABLED": "true",
            "TAX_PERCENTAGE": "18.0",
            "CURRENCY": "INR",
            "REMINDER_DAYS": "7,3,1",
            "SUBSCRIPTION_ENFORCEMENT_MODE": "BLOCK",  # BLOCK vs READ_ONLY
            "STUDENT_COUNTING_RULE": "ACTIVE_ONLY",
        }
        for k, v in defaults.items():
            SubscriptionSetting.objects.get_or_create(key=k, defaults={"value": v})

        settings_qs = SubscriptionSetting.objects.all()
        return Response(SubscriptionSettingSerializer(settings_qs, many=True).data)

    @action(detail=False, methods=["post"], url_path="update-bulk")
    def update_bulk(self, request):
        settings_dict = request.data
        updated = []
        for k, v in settings_dict.items():
            setting_obj, _ = SubscriptionSetting.objects.get_or_create(key=k)
            setting_obj.value = str(v)
            setting_obj.save()
            updated.append(setting_obj)

        AuditLogService.log(
            action="SETTINGS_UPDATED",
            user=request.user,
            new_values=settings_dict,
        )

        return Response({"message": "SaaS settings updated successfully.", "settings": SubscriptionSettingSerializer(updated, many=True).data})
