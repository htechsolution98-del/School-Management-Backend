"""Shared validation helpers used across the API.

Keeping the mobile rules in one place guarantees that the school form, staff
records, OTP registration and login all enforce the exact same rule instead of
each serializer re-implementing (and slowly diverging on) its own regex.
"""

import re

from rest_framework import serializers

MOBILE_LENGTH = 10
MOBILE_ERROR_MESSAGE = "Enter a valid 10-digit mobile number."

# Formatting characters users commonly paste in ("+91 98765-43210", "(98765) 43210").
_SEPARATORS = re.compile(r"[\s()\-\.]")
_DIGITS_ONLY = re.compile(r"^[0-9]{%d}$" % MOBILE_LENGTH)


def normalize_mobile(value):
    """Remove formatting separators so only the meaningful characters remain."""
    if value is None:
        return ""
    return _SEPARATORS.sub("", str(value)).strip()


def is_valid_mobile(value):
    """True when the value is exactly 10 numeric digits."""
    return bool(_DIGITS_ONLY.fullmatch(normalize_mobile(value)))


def validate_mobile(value, *, required=False):
    """
    Validate a mobile number and return its normalized form.

    Meant to be called from a serializer's ``validate_<field>()`` hook, so it
    raises a bare message that DRF nests under the field being validated.
    """
    normalized = normalize_mobile(value)

    if not normalized:
        if required:
            raise serializers.ValidationError("Mobile number is required.")
        return ""

    if not _DIGITS_ONLY.fullmatch(normalized):
        raise serializers.ValidationError(MOBILE_ERROR_MESSAGE)

    return normalized