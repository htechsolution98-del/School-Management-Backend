"""Store eligible text values in lowercase.

The write path already lowercases these fields (see `sms_app.text_normalization`),
this migration brings historical rows in line. Rows use bulk SQL updates so the
operation stays fast on large tables.

Unique fields need a collision check first: when two rows differ only by casing,
the first row keeps the lowercase value and the later ones keep their original
casing so no record is lost and no unique constraint is violated.
"""

from django.db import migrations
from django.db.models import CharField, EmailField, TextField
from django.db.models.functions import Lower


def normalize_text(apps, schema_editor):
    from sms_app.text_normalization import EXCLUDED_FIELD_NAMES, NORMALIZED_FIELD_NAMES

    for model in apps.get_models():
        fields = [
            field
            for field in model._meta.get_fields()
            if getattr(field, "concrete", False)
            and isinstance(field, (CharField, TextField, EmailField))
            and field.name in NORMALIZED_FIELD_NAMES
            and field.name not in EXCLUDED_FIELD_NAMES
        ]
        if not fields:
            continue

        for field in fields:
            manager = model._default_manager
            if field.unique:
                _normalize_unique(manager, field)
            else:
                manager.filter(**{f"{field.name}__isnull": False}).exclude(
                    **{f"{field.name}": ""}
                ).update(**{field.name: Lower(field.name)})


def _normalize_unique(manager, field):
    seen = set()
    rows = manager.exclude(**{f"{field.name}__isnull": True}).order_by("pk").only(
        "pk", field.name
    )
    for obj in rows.iterator(chunk_size=1000):
        original = getattr(obj, field.name, None)
        if not isinstance(original, str) or not original:
            continue
        lowered = original.lower()
        if lowered == original:
            seen.add(lowered)
            continue
        if lowered in seen:
            # Another row already owns the lowercase value; keeping the original
            # casing avoids a unique violation and never drops a record.
            continue
        seen.add(lowered)
        type(obj)._default_manager.filter(pk=obj.pk).update(**{field.name: lowered})


def noop_reverse(apps, schema_editor):
    """Casing is not recoverable; reversing is intentionally a no-op."""


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0022_academicyear_created_at_admission_created_at_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_text, noop_reverse),
    ]