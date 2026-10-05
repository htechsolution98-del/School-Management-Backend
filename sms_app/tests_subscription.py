from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from sms_app.models import (
    School,
    CustomUser,
    Student,
    Module,
    SubscriptionPlan,
    SubscriptionPlanModule,
    SchoolSubscription,
    SchoolInvoice,
    SubscriptionSetting,
)
from sms_app.subscription_services import SubscriptionBillingService


class SubscriptionSystemTest(TestCase):
    def setUp(self):
        # Create user & school
        self.user = CustomUser.objects.create_user(
            username="schooladmin",
            email="admin@school.com",
            password="Password123",
            role="ADMIN"
        )
        self.school = School.objects.create(
            name="Green Valley School",
            code="GVS",
            login_id=self.user
        )
        self.user.school = self.school
        self.user.save()

        # Create modules
        self.mod_students = Module.objects.create(name="Students", code="STUDENT")
        self.mod_fees = Module.objects.create(name="Fees", code="FEES")
        self.mod_transport = Module.objects.create(name="Transport", code="TRANSPORT")

        # Create subscription plan
        self.plan = SubscriptionPlan.objects.create(
            name="Professional",
            pricing_model="PER_STUDENT",
            monthly_price=Decimal("20.00"),
            quarterly_price=Decimal("18.00"),
            half_yearly_price=Decimal("16.00"),
            yearly_price=Decimal("15.00"),
            max_students=5,
            max_teachers=10,
        )
        SubscriptionPlanModule.objects.create(plan=self.plan, module=self.mod_students, is_enabled=True)
        SubscriptionPlanModule.objects.create(plan=self.plan, module=self.mod_fees, is_enabled=True)

        # Set settings
        SubscriptionSetting.objects.create(key="TAX_ENABLED", value="true")
        SubscriptionSetting.objects.create(key="TAX_PERCENTAGE", value="18.0")

    def test_trial_assignment(self):
        today = timezone.now().date()
        sub = SchoolSubscription.objects.create(
            school=self.school,
            plan_type="TRIAL",
            billing_model="FLAT",
            billing_cycle="MONTHLY",
            flat_amount=Decimal("5000.00"),
            start_date=today,
            due_date=today + timedelta(days=14),
            status="TRIAL",
        )
        self.assertTrue(sub.is_valid_now())
        self.assertEqual(sub.days_remaining(), 14)

    def test_billing_calculation_per_student(self):
        # Add 3 active students
        for i in range(3):
            Student.objects.create(
                school=self.school,
                surname="Doe",
                name=f"Child {i}",
                gr_no=f"GR-{i}",
                is_active=True,
            )

        bill = SubscriptionBillingService.calculate_bill(
            school=self.school,
            plan=self.plan,
            billing_cycle="MONTHLY"
        )
        # Monthly per student = 3 students * 20 * 1 month = 60 subtotal
        self.assertEqual(bill["student_count"], 3)
        self.assertEqual(bill["subtotal"], 60.0)
        # Tax = 18% of 60 = 10.8 -> Final = 70.8
        self.assertEqual(bill["tax_amount"], 10.8)
        self.assertEqual(bill["final_amount"], 70.8)

    def test_student_limit_check(self):
        sub = SchoolSubscription.objects.create(
            school=self.school,
            plan=self.plan,
            plan_type="PAID",
            due_date=timezone.now().date() + timedelta(days=30),
            status="ACTIVE"
        )
        # Add max students (5)
        for i in range(5):
            Student.objects.create(
                school=self.school,
                surname="Smith",
                name=f"Student {i}",
                gr_no=f"GR-S-{i}",
                is_active=True
            )
        self.assertEqual(sub.get_live_student_count(), 5)

    def test_price_snapshot_isolation(self):
        bill = SubscriptionBillingService.calculate_bill(
            school=self.school,
            plan=self.plan,
            billing_cycle="MONTHLY"
        )
        snapshot = bill["price_snapshot"]
        self.assertEqual(snapshot["unit_rate"], 20.0)

        # Update plan price afterwards
        self.plan.monthly_price = Decimal("30.00")
        self.plan.save()

        # Original snapshot remains 20.0
        self.assertEqual(snapshot["unit_rate"], 20.0)
