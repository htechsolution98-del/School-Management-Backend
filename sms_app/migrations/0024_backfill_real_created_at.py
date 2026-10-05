"""Replace placeholder creation timestamps on legacy rows with real ones.

Migration 0022 added `created_at` to 54 tables, so existing rows were backfilled
with the moment the column was added rather than the real creation time. This
migration clears those placeholders and restores a real timestamp only when the
model already stores an authoritative one (e.g. Admission.submitted_at).

Rows without a recoverable creation time keep NULL, and the tables render them as
"—" instead of a fabricated date. New rows keep getting a real timestamp from
`auto_now_add`.
"""

from django.db import migrations
from django.db.models import DateTimeField, F

#: Models that received `created_at` in migration 0022.
MODELS_ADDED_IN_0022 = [
    "AcademicYear",
    "Admission",
    "AdmissionDocument",
    "AdmissionFeeStructure",
    "AdmissionFieldValue",
    "AssignClass",
    "Attendance",
    "AttendanceLocation",
    "AttendanceTimeRule",
    "BookIssued",
    "BreakSlot",
    "CertificateTemplateField",
    "CertificateType",
    "ClassCategory",
    "Division",
    "DocumentField",
    "Feature",
    "FeeType",
    "FeeWiseClass",
    "FormField",
    "FormSection",
    "Holiday",
    "HomeworkSubmissions",
    "LateBookFees",
    "LeavePerDay",
    "LeaveTemplate",
    "LectureSlot",
    "Module",
    "Perents",
    "Procurement",
    "ProcurementItem",
    "RazorPayData",
    "SalaryComponent",
    "SchoolClass",
    "SchoolFeature",
    "Slot",
    "StaffRemainingLeave",
    "StaffSalaryComponent",
    "StockRequest",
    "StudentDocument",
    "StudentFieldValue",
    "StudentVerify",
    "Subject",
    "Syllabus",
    "Time_table",
    "Time_Table_tb",
    "TimetableEntry",
    "Tt_breaks",
    "Tt_day",
    "Tt_day_time",
    "Tt_slot",
    "Tt_year",
    "UserModuleAccess",
    "WorkingDay",
]

#: model name -> datetime field holding the authoritative creation time.
BACKFILL_SOURCES = {
    "Admission": "submitted_at",
    "AdmissionDocument": "uploaded_at",
    "HomeworkSubmissions": "submitted_at",
}


def _field_map(model):
    return {
        field.name: field
        for field in model._meta.get_fields()
        if getattr(field, "concrete", False)
    }


def backfill_created_at(apps, schema_editor):
    for model_name in MODELS_ADDED_IN_0022:
        model = apps.get_model("sms_app", model_name)
        fields = _field_map(model)
        if "created_at" not in fields:
            continue
        model._default_manager.all().update(created_at=None)

    for model_name, source_field in BACKFILL_SOURCES.items():
        model = apps.get_model("sms_app", model_name)
        fields = _field_map(model)
        if "created_at" not in fields:
            continue
        if not isinstance(fields.get(source_field), DateTimeField):
            continue
        model._default_manager.filter(
            **{f"{source_field}__isnull": False}
        ).update(created_at=F(source_field))


def noop_reverse(apps, schema_editor):
    """Placeholder values are not worth restoring."""


class Migration(migrations.Migration):

    dependencies = [
        ("sms_app", "0023_lowercase_normalized_text"),
    ]

    operations = [
        migrations.RunPython(backfill_created_at, noop_reverse),
    ]