from rest_framework import serializers
from .models import School, SchoolSubscription, SchoolInvoice, Student
from django.utils import timezone


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
            "student_count",
            "unit_rate",
            "subtotal",
            "tax_amount",
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


class SchoolSubscriptionSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)
    school_email = serializers.CharField(source="school.email", read_only=True)
    school_phone = serializers.CharField(source="school.phone", read_only=True)
    school_city = serializers.CharField(source="school.city", read_only=True)
    school_is_active = serializers.BooleanField(source="school.is_active", read_only=True)

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
            "plan_type",
            "billing_model",
            "billing_cycle",
            "flat_amount",
            "per_student_rate",
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
