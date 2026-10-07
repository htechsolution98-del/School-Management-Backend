"""Admission field validation shared by online and clerk submissions."""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import unicodedata


def validate_admission_upload(file):
    extension = str(getattr(file, "name", "")).rsplit(".", 1)[-1].lower()
    content_type = getattr(file, "content_type", "")
    if extension not in ("pdf", "png", "jpg", "jpeg", "webp") or content_type not in ("", "application/pdf", "image/png", "image/jpeg", "image/webp"):
        return "Upload PDF, JPG, PNG or WebP files only"
    size = getattr(file, "size", 0)
    limit = (3 if extension == "pdf" else 1) * 1024 * 1024
    if size <= 0 or size > limit:
        return "PDF must be up to 3 MB and images up to 1 MB; empty files are not allowed"
    return ""


def validate_admission_value(field, raw_value, today=None):
    value = str(raw_value if raw_value is not None else "").strip()
    label = field.label
    mapping = field.map_to_student_field or ""
    kind = field.field_type
    descriptor = f"{label} {mapping}".lower()
    if kind == "checkbox":
        if value.lower() not in ("", "true", "false", "yes", "no", "1", "0"):
            return value, "Use Yes or No"
        checked = value.lower() in ("true", "yes", "1")
        return str(checked).lower(), f"{label} must be checked" if field.is_required and not checked else ""
    if not value:
        return value, f"{label} is required" if field.is_required else ""
    if len(value) > (2000 if kind == "textarea" else 255):
        return value, f"{label} is too long"
    aadhaar = bool(re.search(r"aadh?aar|aadhar", descriptor))
    phone = kind == "tel" or bool(re.search(r"mobile|phone|contact.number|whatsapp", descriptor))
    pincode = bool(re.search(r"pin\s*code|pincode|postal", label, re.I))
    if aadhaar:
        value = re.sub(r"[\s-]", "", value)
        if not re.fullmatch(r"\d{12}", value):
            return value, "Aadhaar must contain exactly 12 digits"
    if phone:
        value = re.sub(r"[\s()-]", "", value)
        if re.fullmatch(r"\+91\d{10}", value):
            value = value[3:]
        if not re.fullmatch(r"[6-9]\d{9}", value):
            return value, "Enter a valid 10-digit mobile number"
    if kind == "email" or re.search(r"email|e-mail", descriptor):
        value = value.lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", value):
            return value, "Enter a valid email address"
    if pincode and not re.fullmatch(r"[1-9]\d{5}", value):
        return value, "Enter a valid 6-digit PIN code"
    if kind == "number" and not (aadhaar or phone or pincode):
        try:
            if not re.fullmatch(r"\d+(\.\d+)?", value) or not Decimal(value).is_finite():
                return value, "Enter a valid non-negative number"
        except InvalidOperation:
            return value, "Enter a valid non-negative number"
    birth = mapping == "date_of_birth" or bool(re.search(r"\bbirth\b|\bdob\b", label, re.I))
    if kind == "date" or birth:
        parsed = None
        for format_string in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = datetime.strptime(value, format_string).date()
                break
            except ValueError:
                pass
        if not parsed or parsed.year < 1900:
            return value, "Enter a real date in DD/MM/YYYY format"
        if birth and parsed >= (today or date.today()):
            return value, "Date of birth must be before today"
        value = parsed.isoformat()
    is_name = mapping in ("name", "surname", "father_name", "mother_name") or bool(re.fullmatch(r"(student |full |father'?s? |mother'?s? |guardian'?s? )?name", label, re.I))
    if is_name and (not value[0].isalpha() or any(not (char.isalpha() or unicodedata.category(char).startswith("M") or char.isspace() or char in ".'’-" ) for char in value)):
        return value, "Use letters, spaces, apostrophes, dots or hyphens for names"
    if kind in ("select", "radio") and isinstance(field.options, list) and field.options:
        allowed = [str(option.get("value", option.get("label", ""))) if isinstance(option, dict) else str(option) for option in field.options]
        if value not in allowed:
            return value, "Choose an available option"
    return value, ""
