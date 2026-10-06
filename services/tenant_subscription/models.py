from django.db import models


class Feature(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tenant_feature"

    def __str__(self):
        return self.name


class Module(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = "tenant_module"

    def __str__(self):
        return self.name


class School(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    address = models.TextField()
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant_school"

    def __str__(self):
        return self.name


class SchoolFeature(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="school_features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "tenant_school_feature"
        unique_together = ("school", "feature")


class SubscriptionPlan(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_days = models.IntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "tenant_subscription_plan"


class SubscriptionPlanModule(models.Model):
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="plan_modules")
    module = models.ForeignKey(Module, on_delete=models.CASCADE)

    class Meta:
        db_table = "tenant_subscription_plan_module"


class SchoolSubscription(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "tenant_school_subscription"


class SchoolInvoice(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="invoices")
    invoice_number = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)

    class Meta:
        db_table = "tenant_school_invoice"


class SubscriptionPayment(models.Model):
    invoice = models.ForeignKey(SchoolInvoice, on_delete=models.CASCADE, related_name="payments")
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=50, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant_subscription_payment"


class SubscriptionAuditLog(models.Model):
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tenant_subscription_audit_log"


class SubscriptionSetting(models.Model):
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()

    class Meta:
        db_table = "tenant_subscription_setting"
