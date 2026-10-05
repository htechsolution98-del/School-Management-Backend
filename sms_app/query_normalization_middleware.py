"""
Lowercase incoming filter/search query parameters.

Text is stored lowercase (see `sms_app.text_normalization`), so any lookup sent
by the frontend must be lowercased too. Otherwise a filter for "Ahemdabad" would
never match the stored "ahemdabad" row.

Only parameters whose names correspond to normalized fields are touched, so
enum-like filters (status, category, payment_mode) and identifiers keep working.
"""

from django.utils.deprecation import MiddlewareMixin

from .text_normalization import NORMALIZED_FIELD_NAMES

#: Query parameter names that hold user-entered text.
TEXT_QUERY_PARAMS = frozenset(
    {
        "search",
        "q",
        "query",
        "name",
        "city",
        "state",
        "country",
        "address",
        "school",
        "school_name",
        "school_class",
        "class_name",
        "division",
        "subject",
        "subject_name",
        "religion",
        "scheduled_caste",
        "father_name",
        "mother_name",
        "staff_name",
        "supplier",
        "title",
        "label",
        "field_name",
        "asset_name",
        "index_no",
        "pincode",
        "place_of_birth",
        "last_school",
        "grade",
        "email",
    }
) | set(NORMALIZED_FIELD_NAMES)


class NormalizedQueryMiddleware(MiddlewareMixin):
    """Lowercase text query parameters so filters match lowercase storage."""

    def process_request(self, request):
        params = request.GET
        if not params:
            return None

        changed = False
        normalized = {}
        for key, values in params.lists():
            if key.lower() in TEXT_QUERY_PARAMS:
                lowered = [value.lower() if isinstance(value, str) else value for value in values]
                if lowered != values:
                    changed = True
                normalized[key] = lowered
            else:
                normalized[key] = values

        if changed:
            query = normalized.items()
            request.GET = request.GET.copy()
            for key, _ in query:
                request.GET.pop(key, None)
            for key, values in normalized.items():
                for value in values:
                    request.GET.appendlist(key, value)

        return None