"""
Lowercase storage normalization.

Text that identifies a person, place or label is always stored lowercase so that
"AHEMDABAD", "ahemdabad" and "Ahemdabad" cannot become three separate records.
The frontend renders these values in Camel Case (first letter of every word
uppercased, remaining letters lowercase).

Fields that must keep their exact casing are intentionally excluded:
  * credentials and secrets  -> password, username, otp, razorpay_secret_key
  * generated identifiers    -> code, slug, gr_no, aadhaar_number, receipts,
                                 transaction ids, admission/certificate numbers
  * enum-like values         -> status, category, payment_mode, day, year,
                                 leave_type, fee_type, announcement_for, role
  * free-form long text      -> description, message, note, reason, remarks
                                 (case is part of the content itself)
  * structured payloads      -> options, default_value, value, JSON fields
"""

from django.db import models
from django.db.models.signals import pre_save

#: Field names normalized to lowercase on every save.
NORMALIZED_FIELD_NAMES = frozenset(
    {
        # people
        "name",
        "surname",
        "father_name",
        "mother_name",
        "staff_name",
        "supplier",
        "author",
        "school_name",
        "class_name",
        "subject_name",
        "heading",
        # places
        "city",
        "state",
        "country",
        "address",
        "place_of_birth",
        "last_school",
        "village",
        "district",
        "taluka",
        # labels
        "title",
        "label",
        "field_name",
        "asset_name",
        "religion",
        "scheduled_caste",
        "grade",
        "school_class",
        "division",
        "index_no",
        "pincode",
        # contact (emails are case-insensitive in practice, so they are safe)
        "email",
    }
)

#: Never touch these, even if a same-named field is added to a new model.
EXCLUDED_FIELD_NAMES = frozenset(
    {
        "password",
        "username",
        "otp",
        "slug",
        "code",
        "unique_link",
        "description",
        "message",
        "note",
        "note_text",
        "reason",
        "remark",
        "remarks",
        "issue",
        "progress",
        "conduct",
        "value",
        "options",
        "default_value",
        "status",
        "category",
        "role",
        "day",
        "time",
        "year",
        "grade_code",
        "payment_mode",
        "payment_status",
        "leave_type",
        "fee_type",
        "announcement_for",
        "notification_type",
        "document_type",
        "expense_type",
        "material_type",
        "component_type",
        "calculation_type",
        "late_fee_type",
        "billing_cycle",
        "billing_period",
        "salary_month",
        "currency",
        "transaction_id",
        "receipt_number",
        "admission_number",
        "certificate_number",
        "asset_code",
        "gr_no",
        "aadhar_number",
        "mobile",
        "phone",
        "razorpay_key_id",
        "razorpay_order_id",
        "razorpay_payment_id",
        "razorpay_signature",
        "razorpay_secret_key",
    }
)

_NORMALIZABLE_FIELD_TYPES = (
    models.CharField,
    models.TextField,
    models.EmailField,
)


def normalized_field_names(model: type[models.Model]) -> set[str]:
    """Field names eligible for lowercase storage on the given model."""
    eligible = set()
    for field in model._meta.get_fields():
        if not getattr(field, "concrete", False):
            continue
        if not isinstance(field, _NORMALIZABLE_FIELD_TYPES):
            continue
        if field.name in EXCLUDED_FIELD_NAMES:
            continue
        if field.name in NORMALIZED_FIELD_NAMES:
            eligible.add(field.name)
    return eligible


def normalize_instance(instance: models.Model) -> None:
    """Lowercase every eligible field of an unsaved instance."""
    if instance is None:
        return
    for name in normalized_field_names(type(instance)):
        value = getattr(instance, name, None)
        if isinstance(value, str) and value != value.lower():
            setattr(instance, name, value.lower())


def connect_normalization_signals() -> None:
    """Normalize every model save so the invariant holds for all write paths."""
    pre_save.connect(_normalize_before_save, dispatch_uid="sms_app.lowercase_text")


def _normalize_before_save(sender: type[models.Model], instance: models.Model, **kwargs) -> None:
    normalize_instance(instance)