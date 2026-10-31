from rest_framework import serializers
from .school_profile_models import SchoolProfile


class SchoolProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for SchoolProfile model covering institutional identity,
    banking/billing, and official media branding assets.
    """
    school_id = serializers.IntegerField(source="school.id", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)

    class Meta:
        model = SchoolProfile
        fields = [
            "id",
            "school_id",
            "school_name",
            "school_code",
            # Basic Info
            "school_full_name",
            "school_short_name",
            "tagline",
            "establishment_year",
            "board_affiliation",
            "udise_code",
            # Contact Info
            "full_address",
            "phone_numbers",
            "official_emails",
            "website_url",
            # Billing & Bank Info
            "trust_name",
            "pan_gst_number",
            "bank_account_name",
            "bank_account_no",
            "bank_ifsc",
            "bank_name",
            # Media (Cloudinary URLs)
            "main_logo_url",
            "print_logo_url",
            "favicon_url",
            "login_banner_url",
            "certificate_watermark_url",
            "receipt_bg_url",
            "principal_signature_url",
            "trustee_signature_url",
            "official_seal_url",
            # Timestamps
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "school_id", "school_name", "school_code", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Synchronize base School entity attributes if updated
        school = instance.school
        updated_school = False
        if "school_full_name" in validated_data and validated_data["school_full_name"]:
            school.name = validated_data["school_full_name"]
            updated_school = True
        if "full_address" in validated_data and validated_data["full_address"]:
            school.address = validated_data["full_address"]
            updated_school = True
        if "phone_numbers" in validated_data and validated_data["phone_numbers"]:
            # If multiple comma separated, pick primary or full
            primary_phone = validated_data["phone_numbers"].split(",")[0].strip()
            if primary_phone and len(primary_phone) <= 25:
                school.phone = primary_phone
                updated_school = True
        if "official_emails" in validated_data and validated_data["official_emails"]:
            primary_email = validated_data["official_emails"].split(",")[0].strip()
            if primary_email:
                school.email = primary_email
                updated_school = True

        if updated_school:
            school.save(update_fields=[f for f in ["name", "address", "phone", "email"] if getattr(school, f, None)])

        return instance

