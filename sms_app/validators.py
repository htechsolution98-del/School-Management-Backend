"""Shared validation helpers used across the API.

Keeping the mobile and password rules in one place guarantees that the school form,
staff records, OTP registration, reset password and profile all enforce the exact
same rules instead of each serializer re-implementing its own divergent logic.
"""

import re
from rest_framework import serializers

MOBILE_LENGTH = 10
MOBILE_ERROR_MESSAGE = "Enter a valid 10-digit mobile number starting with 6, 7, 8, or 9."

# Formatting characters users commonly paste in ("+91 98765-43210", "(98765) 43210").
_SEPARATORS = re.compile(r"[\s()\-\.]")
_MOBILE_REGEX = re.compile(r"^[6-9][0-9]{9}$")


def normalize_mobile(value):
    """Remove formatting separators and standard prefixes so only 10 digits remain."""
    if value is None:
        return ""
    val = _SEPARATORS.sub("", str(value)).strip()
    if val.startswith("+91"):
        val = val[3:]
    elif val.startswith("91") and len(val) == 12:
        val = val[2:]
    elif val.startswith("0") and len(val) == 11:
        val = val[1:]
    return val


def is_valid_mobile(value):
    """True when the value is exactly 10 digits starting with 6, 7, 8, or 9."""
    return bool(_MOBILE_REGEX.fullmatch(normalize_mobile(value)))


def validate_mobile(value, *, required=False):
    """
    Validate a mobile number and return its normalized form.

    Enforces 10 digits starting with 6, 7, 8, or 9.
    """
    normalized = normalize_mobile(value)

    if not normalized:
        if required:
            raise serializers.ValidationError("Mobile number is required.")
        return ""

    if not _MOBILE_REGEX.fullmatch(normalized):
        if len(normalized) != 10:
            raise serializers.ValidationError("Mobile number must be exactly 10 digits.")
        if normalized[0] not in "6789":
            raise serializers.ValidationError("Mobile number must start with 6, 7, 8, or 9.")
        raise serializers.ValidationError(MOBILE_ERROR_MESSAGE)

    return normalized


def validate_strong_password(password: str) -> str:
    """
    Validate that password meets strong security criteria:
    - At least 8 characters long
    - At least one uppercase letter (A-Z)
    - At least one lowercase letter (a-z)
    - At least one digit (0-9)
    - At least one special character
    """
    pwd = str(password or "").strip()
    if not pwd:
        raise serializers.ValidationError("Password is required.")
    if len(pwd) < 8:
        raise serializers.ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", pwd):
        raise serializers.ValidationError("Password must contain at least one uppercase letter (A-Z).")
    if not re.search(r"[a-z]", pwd):
        raise serializers.ValidationError("Password must contain at least one lowercase letter (a-z).")
    if not re.search(r"\d", pwd):
        raise serializers.ValidationError("Password must contain at least one number (0-9).")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>\-_+=\[\]\\;'`~]", pwd):
        raise serializers.ValidationError("Password must contain at least one special character (!@#$%^&* etc.).")
    return pwd
