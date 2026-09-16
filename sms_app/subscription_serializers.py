from rest_framework import serializers
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


class ModuleMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Module
        fields = ["id", "name", "code", "description"]


class SubscriptionPlanModuleSerializer(serializers.ModelSerializer):
    module_details = ModuleMinimalSerializer(source="module", read_only=True)
    module_code = serializers.CharField(source="module.code", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True)

    class Meta:
        model = SubscriptionPlanModule
        fields = ["id", "plan", "module", "module_code", "module_name", "module_details", "is_enabled"]


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    plan_modules = SubscriptionPlanModuleSerializer(many=True, read_only=True)
    enabled_module_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    subscribed_schools_count = serializers.SerializerMethodField()

    class Meta:
        model = SubscriptionPlan
        fields = [
            "id",
            "name",
            "description",
            "pricing_model",
            "monthly_price",
            "quarterly_price",
            "half_yearly_price",
            "yearly_price",
            "trial_available",
            "trial_duration_days",
            "max_students",
            "max_teachers",
            "max_staff",
            "max_admin_users",
            "storage_limit_mb",
            "is_active",
            "plan_modules",
            "enabled_module_ids",
            "subscribed_schools_count",
            "created_at",
            "updated_at",
        ]

    def get_subscribed_schools_count(self, obj):
        return obj.school_subscriptions.count()

    def create(self, validated_data):
        module_ids = validated_data.pop("enabled_module_ids", [])
        plan = SubscriptionPlan.objects.create(**validated_data)
        if module_ids:
            for mod_id in module_ids:
                try:
                    mod = Module.objects.get(id=mod_id)
                    SubscriptionPlanModule.objects.create(plan=plan, module=mod, is_enabled=True)
                except Module.DoesNotExist:
                    pass
        return plan

    def update(self, instance, validated_data):
        module_ids = validated_data.pop("enabled_module_ids", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if module_ids is not None:
            # Sync plan modules
            SubscriptionPlanModule.objects.filter(plan=instance).delete()
            for mod_id in module_ids:
                try:
                    mod = Module.objects.get(id=mod_id)
                    SubscriptionPlanModule.objects.create(plan=instance, module=mod, is_enabled=True)
                except Module.DoesNotExist:
                    pass
        return instance


class SchoolSubscriptionSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)
    school_email = serializers.CharField(source="school.email", read_only=True)
    school_phone = serializers.CharField(source="school.phone", read_only=True)
    school_city = serializers.CharField(source="school.city", read_only=True)
    school_is_active = serializers.BooleanField(source="school.is_active", read_only=True)

    plan_name = serializers.CharField(source="plan.name", read_only=True)
    live_student_count = serializers.SerializerMethodField()
    calculated_amount = serializers.SerializerMethodField()
    days_left = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()

    class Meta:
        model = SchoolSubscription
        fields = [
            "id",
            "school",
            "school_name",
            "school_code",
            "school_email",
            "school_phone",
            "school_city",
            "school_is_active",
            "plan",
            "plan_name",
            "plan_type",
            "billing_model",
            "billing_cycle",
            "flat_amount",
            "per_student_rate",
            "student_count_at_purchase",
            "price_snapshot",
            "trial_start_date",
            "trial_end_date",
            "subscription_start_date",
            "subscription_end_date",
            "start_date",
            "due_date",
            "grace_period_days",
            "status",
            "auto_lock_on_due",
            "notes",
            "live_student_count",
            "calculated_amount",
            "days_left",
            "is_valid",
            "created_at",
            "updated_at",
        ]

    def get_live_student_count(self, obj):
        return obj.get_live_student_count()

    def get_calculated_amount(self, obj):
        return obj.calculate_current_amount()

    def get_days_left(self, obj):
        return obj.days_remaining()

    def get_is_valid(self, obj):
        return obj.is_valid_now()


class SchoolInvoiceSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)

    class Meta:
        model = SchoolInvoice
        fields = [
            "id",
            "school",
            "school_name",
            "school_code",
            "subscription",
            "invoice_number",
            "billing_model",
            "billing_cycle",
            "student_count",
            "unit_rate",
            "subtotal",
            "tax_percentage",
            "tax_amount",
            "discount_amount",
            "total_amount",
            "billing_period_start",
            "billing_period_end",
            "due_date",
            "status",
            "paid_at",
            "payment_method",
            "payment_reference",
            "notes",
            "created_at",
            "updated_at",
        ]


class SubscriptionPaymentSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = SubscriptionPayment
        fields = [
            "id",
            "payment_id",
            "school",
            "school_name",
            "subscription",
            "invoice",
            "invoice_number",
            "transaction_id",
            "gateway",
            "amount",
            "currency",
            "status",
            "payment_method",
            "paid_at",
            "failure_reason",
            "metadata",
            "created_at",
            "updated_at",
        ]


class SubscriptionAuditLogSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = SubscriptionAuditLog
        fields = [
            "id",
            "school",
            "school_name",
            "user",
            "user_name",
            "action",
            "old_values",
            "new_values",
            "notes",
            "timestamp",
        ]


class SubscriptionSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionSetting
        fields = ["id", "key", "value", "description", "updated_at"]
