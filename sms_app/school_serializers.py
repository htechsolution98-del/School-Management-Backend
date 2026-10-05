from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import *
from .validators import validate_mobile
import re

User = get_user_model()

class FeatureSerialzer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = "__all__"

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Feature name must contain at least 2 characters.")
        if Feature.objects.filter(name__iexact=value).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError("This feature already exists.")
        return value


# -----------FOR SET WHICH FEATURE SCHOOL HAS-----------


class SchoolFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source="feature.name", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "school", "feature", "feature_name", "is_enabled",
            "created_at"
        ]
        read_only_fields = ["is_enabled", "feature_name"]

    def validate(self, data):
        school = data.get("school")
        feature = data.get("feature")

        if SchoolFeature.objects.filter(school=school, feature=feature).exists():
            raise serializers.ValidationError(
                {"message": "This Feature already have to this school"}
            )
        return data


# -----------TO GET FEATURE FRO DROP DOWN IN STAFF CREATE---------------


class GetFeatureSerializer(serializers.ModelSerializer):

    feature_name = serializers.CharField(source="feature.name", read_only=True)
    feature_id = serializers.CharField(source="feature.id", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "feature_id", "feature_name",
            "created_at"
        ]


from rest_framework import serializers




class ChangeFeatureStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolFeature
        fields = ["is_enabled",
            "created_at"
        ]




class SchoolSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(max_length=25, error_messages={"blank": "Phone number is required.", "required": "Phone number is required."})
    feature_ids = serializers.PrimaryKeyRelatedField(
        queryset=Feature.objects.all(), many=True, write_only=True, allow_empty=False,
        error_messages={"empty": "Select at least one feature.", "required": "Select at least one feature."},
    )
    school_features = SchoolFeatureSerializer(
        source="schoolfeature_set", many=True, read_only=True
    )

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "slug",
            "code",
            "feature_ids",
            "address",
            "city",
            "state",
            "country",
            "pincode",
            "logo",
            "index_no",
            "is_active",
            "school_features",
            "created_at"
        ]
        read_only_fields = ["slug", "code"]
        extra_kwargs = {
            field: {"required": True, "allow_blank": False, "allow_null": False,
                    "error_messages": {"required": f"{label} is required.", "blank": f"{label} is required.", "null": f"{label} is required."}}
            for field, label in [("name", "School name"), ("email", "Email"), ("address", "Address"),
                                 ("city", "City"), ("state", "State"), ("country", "Country"), ("pincode", "Postal code")]
        }
        extra_kwargs["email"]["error_messages"]["invalid"] = "Enter a valid email address."
        extra_kwargs["is_active"] = {"allow_null": False, "default": True}

    def validate_name(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("School name must contain at least 2 characters.")
        return value.strip()

    def validate_email(self, value):
        value = value.strip().lower()
        users = User.objects.filter(email__iexact=value)
        schools = School.objects.filter(email__iexact=value)
        if self.instance:
            users = users.exclude(pk=self.instance.login_id_id)
            schools = schools.exclude(pk=self.instance.pk)
        if users.exists() or schools.exists():
            raise serializers.ValidationError("This email is already used by another account or school.")
        return value

    def validate_phone(self, value):
        value = validate_mobile(value, required=True)
        # The school phone doubles as the login user's mobile number, so it has
        # to stay unique across accounts (CustomUser.mobile is UNIQUE).
        users = User.objects.filter(mobile=value)
        if self.instance and self.instance.login_id_id:
            users = users.exclude(pk=self.instance.login_id_id)
        if users.exists():
            raise serializers.ValidationError(
                "This mobile number is already used by another account."
            )
        return value

    def validate_address(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Address must contain at least 5 characters.")
        return value.strip()

    def validate_index_no(self, value):
        if value and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /_-]*", value.strip()):
            raise serializers.ValidationError("Use letters, numbers, spaces, hyphens, underscores or slashes for the index number.")
        return value.strip() if value else value

    def validate_logo(self, value):
        if value and value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Logo must be 2 MB or smaller.")
        if value and getattr(value.image, "format", None) not in {"PNG", "JPEG", "WEBP"}:
            raise serializers.ValidationError("Upload a valid PNG, JPEG or WebP image.")
        return value

    def validate(self, data):
        errors = {}
        for field in ("city", "state", "country"):
            if field in data and len(data[field].strip()) < 2:
                errors[field] = f"{field.title()} must contain at least 2 characters."
        pincode = data.get("pincode", getattr(self.instance, "pincode", None))
        country = data.get("country", getattr(self.instance, "country", "")) or ""
        if "pincode" in data or "country" in data:
            if country.strip().lower() in {"india", "in", "bharat"}:
                if not pincode or not re.fullmatch(r"[1-9][0-9]{5}", pincode):
                    errors["pincode"] = "Enter a valid 6-digit Indian PIN code."
            elif not pincode or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 -]{1,9}", pincode):
                errors["pincode"] = "Enter a postal code of 2 to 10 letters or numbers."
        if errors:
            raise serializers.ValidationError(errors)
        return data

    def validate_feature_ids(self, value):
        ids = [f.id for f in value]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate features are not allowed.")

        return value




class SchoolListSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "logo", "index_no",
            "created_at"
        ]




