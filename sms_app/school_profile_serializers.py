import re
import json
import datetime
from rest_framework import serializers
from .school_profile_models import SchoolProfile

INDIAN_MOBILE_REGEX = re.compile(r"^[6-9]\d{9}$")
REPEATING_DIGITS_REGEX = re.compile(r"^([6-9])\1{9}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
BANK_ACC_REGEX = re.compile(r"^\d{9,18}$")
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
MAX_ASSET_FILE_SIZE = 200 * 1024  # 204,800 bytes (200 KB)

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}

ALLOWED_FAVICON_CONTENT_TYPES = ALLOWED_IMAGE_CONTENT_TYPES | {
    "image/x-icon",
    "image/vnd.microsoft.icon",
}

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FAVICON_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | {".ico"}



class SchoolProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for SchoolProfile model covering institutional identity,
    banking/billing, and official media branding assets with strict validation.
    """
    school_id = serializers.IntegerField(source="school.id", read_only=True)
    school_name = serializers.CharField(source="school.name", read_only=True)
    school_code = serializers.CharField(source="school.code", read_only=True)
    phone_numbers = serializers.JSONField(required=False, allow_null=True)
    board_affiliation = serializers.JSONField(required=False, allow_null=True)

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

    def validate_school_full_name(self, value):
        if value is not None:
            clean = str(value).strip()
            if not clean:
                raise serializers.ValidationError("School full name is required.")
            if len(clean) < 2:
                raise serializers.ValidationError("School full name must be at least 2 characters.")
            return clean
        return value

    def validate_establishment_year(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        if not clean.isdigit() or len(clean) != 4:
            raise serializers.ValidationError("Establishment year must be a valid 4-digit number (e.g. 1998).")
        year = int(clean)
        current_year = datetime.datetime.now().year
        if year < 1800 or year > current_year:
            raise serializers.ValidationError(
                f"Establishment year must be between 1800 and {current_year}."
            )
        return clean

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        raw = instance.phone_numbers
        if not raw:
            ret["phone_numbers"] = []
        elif isinstance(raw, list):
            ret["phone_numbers"] = raw
        elif isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    ret["phone_numbers"] = [str(x) for x in parsed]
                else:
                    ret["phone_numbers"] = [p.strip() for p in raw.split(",") if p.strip()]
            except Exception:
                ret["phone_numbers"] = [p.strip() for p in raw.split(",") if p.strip()]
        else:
            ret["phone_numbers"] = []

        raw_board = instance.board_affiliation
        if not raw_board:
            ret["board_affiliation"] = []
        elif isinstance(raw_board, list):
            ret["board_affiliation"] = raw_board
        elif isinstance(raw_board, str):
            try:
                parsed = json.loads(raw_board)
                if isinstance(parsed, list):
                    ret["board_affiliation"] = [str(x) for x in parsed]
                else:
                    ret["board_affiliation"] = [raw_board.strip()] if raw_board.strip() else []
            except Exception:
                ret["board_affiliation"] = [raw_board.strip()] if raw_board.strip() else []
        else:
            ret["board_affiliation"] = []
        return ret

    def validate_phone_numbers(self, value):
        if value in (None, "", [], "[]"):
            return "[]"
        phone_list = []
        if isinstance(value, str):
            clean_str = value.strip()
            if not clean_str:
                return "[]"
            try:
                parsed = json.loads(clean_str)
                if isinstance(parsed, list):
                    phone_list = parsed
                else:
                    phone_list = [clean_str]
            except Exception:
                phone_list = [p.strip() for p in clean_str.split(",") if p.strip()]
        elif isinstance(value, (list, tuple)):
            phone_list = list(value)
        else:
            raise serializers.ValidationError("Phone numbers must be an array of strings.")

        cleaned_phones = []
        for p in phone_list:
            if p is None:
                continue
            item = str(p).strip()
            if not item:
                continue
            digits = re.sub(r"\D", "", item)
            if not INDIAN_MOBILE_REGEX.match(digits) or REPEATING_DIGITS_REGEX.match(digits):
                raise serializers.ValidationError(
                    "Please enter a valid 10-digit Indian phone number starting with 6, 7, 8, or 9."
                )
            cleaned_phones.append(digits)

        json_str = json.dumps(cleaned_phones)
        if len(json_str) > 255:
            raise serializers.ValidationError("Total phone numbers payload exceeds storage limit.")
        return json_str

    def validate_pan_gst_number(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip().upper()
        if not clean:
            return ""
        if len(clean) == 10:
            if not PAN_REGEX.match(clean):
                raise serializers.ValidationError(
                    "Invalid PAN format. Must be 10 characters: 5 uppercase letters, 4 digits, 1 uppercase letter (e.g. ABCDE1234F)."
                )
        elif len(clean) == 15:
            if not GSTIN_REGEX.match(clean):
                raise serializers.ValidationError(
                    "Invalid GSTIN format. Must be 15 characters matching standard Indian GSTIN format (e.g. 24ABCDE1234F1Z5)."
                )
        else:
            raise serializers.ValidationError(
                "Trust PAN / GSTIN must be either a 10-character PAN (e.g. ABCDE1234F) or a 15-character GSTIN (e.g. 24ABCDE1234F1Z5)."
            )
        return clean

    def validate_board_affiliation(self, value):
        if value in (None, "", [], "[]"):
            return []
        board_list = []
        if isinstance(value, str):
            clean_str = value.strip()
            if not clean_str:
                return []
            try:
                parsed = json.loads(clean_str)
                if isinstance(parsed, list):
                    board_list = parsed
                else:
                    board_list = [clean_str]
            except Exception:
                board_list = [clean_str]
        elif isinstance(value, (list, tuple)):
            board_list = list(value)
        else:
            raise serializers.ValidationError("Board affiliation must be an array of strings.")

        cleaned_boards = []
        for b in board_list:
            if b is None:
                continue
            item = str(b).strip()
            if item and item not in cleaned_boards:
                cleaned_boards.append(item)
        return cleaned_boards

    def validate_official_emails(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        emails = [e.strip() for e in clean.split(",") if e.strip()]
        if not emails:
            return ""
        for email in emails:
            if not EMAIL_REGEX.match(email):
                raise serializers.ValidationError(
                    f"'{email}' is not a valid email address. Must contain '@' and a valid domain."
                )
        return ", ".join(emails)

    def validate_bank_account_no(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        if not clean.isdigit():
            raise serializers.ValidationError("Bank account number must contain only numeric characters.")
        if not (9 <= len(clean) <= 18):
            raise serializers.ValidationError("Bank account number must be between 9 and 18 digits.")
        return clean

    def validate_bank_ifsc(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip().upper()
        if not clean:
            return ""
        if not IFSC_REGEX.match(clean):
            raise serializers.ValidationError(
                "Invalid IFSC code. It must be exactly 11 characters in standard Indian format (e.g. HDFC0001234: 4 letters, '0', 6 alphanumeric characters)."
            )
        return clean

    def validate_website_url(self, value):
        if value in (None, ""):
            return ""
        clean = str(value).strip()
        if not clean:
            return ""
        url_pattern = re.compile(
            r"^(https?://)?"
            r"([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}"
            r"(:[0-9]{1,5})?"
            r"(/.*)?$"
        )
        if not url_pattern.match(clean):
            raise serializers.ValidationError("Please provide a valid website URL (e.g. https://www.school.edu).")
        return clean

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
            raw_phones = validated_data["phone_numbers"]
            primary_phone = ""
            if isinstance(raw_phones, list) and raw_phones:
                primary_phone = str(raw_phones[0]).strip()
            elif isinstance(raw_phones, str):
                try:
                    parsed = json.loads(raw_phones)
                    if isinstance(parsed, list) and parsed:
                        primary_phone = str(parsed[0]).strip()
                    else:
                        primary_phone = raw_phones.split(",")[0].strip()
                except Exception:
                    primary_phone = raw_phones.split(",")[0].strip()
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

class SchoolProfileAssetUploadSerializer(serializers.Serializer):
    """
    Validates uploaded media assets for School Profile.
    Strictly enforces a 200 KB maximum file size limit (204,800 bytes)
    and restricts MIME types and extensions to allowed image formats.
    """
    file = serializers.FileField(required=True)
    asset_type = serializers.CharField(required=False, default="branding")

    def validate_file(self, value):
        if not value:
            raise serializers.ValidationError("No file uploaded.")

        if value.size > MAX_ASSET_FILE_SIZE:
            raise serializers.ValidationError("File size must not exceed 200 KB.")

        # Determine asset type from initial data
        asset_type = ""
        if hasattr(self, "initial_data") and isinstance(self.initial_data, dict):
            asset_type = str(self.initial_data.get("asset_type", "")).lower()

        is_favicon = "favicon" in asset_type

        # Check file extension
        import os
        filename = getattr(value, "name", "")
        _, ext = os.path.splitext(filename.lower())
        allowed_exts = ALLOWED_FAVICON_EXTENSIONS if is_favicon else ALLOWED_IMAGE_EXTENSIONS

        if ext and ext not in allowed_exts:
            raise serializers.ValidationError(
                f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(allowed_exts))}."
            )

        # Check content type if available
        content_type = getattr(value, "content_type", "").lower()
        allowed_types = ALLOWED_FAVICON_CONTENT_TYPES if is_favicon else ALLOWED_IMAGE_CONTENT_TYPES

        if content_type and content_type not in allowed_types:
            raise serializers.ValidationError(
                f"Unsupported content type '{content_type}'. Allowed types: {', '.join(sorted(allowed_types))}."
            )

        return value
