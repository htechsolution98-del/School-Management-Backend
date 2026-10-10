from django.db.models.signals import post_save
from django.db import IntegrityError
from django.contrib.auth import get_user_model
from django.dispatch import receiver
import logging

from .models import School, Feature, SchoolFeature
from .validators import normalize_mobile, is_valid_mobile

logger = logging.getLogger(__name__)

DEFAULT_FEATURES = [
    "LIBRARIAN",
    "FEES MANAGEMENT",
    "INVENTORY",
    "PRINCIPAL",
    "TRANSPORTATION",
    "TEACHER",
    "CLERK",
    "VICE PRINCIPAL",
    "ASSISTANT CLERK",
]

def seed_features_and_school_features():
    """Ensure all default features exist and are enabled for all schools."""
    feature_objs = []
    for name in DEFAULT_FEATURES:
        feat, _ = Feature.objects.get_or_create(name=name.strip().lower())
        feature_objs.append(feat)

    for school in School.objects.all():
        for feat in feature_objs:
            SchoolFeature.objects.get_or_create(
                school=school,
                feature=feat,
                defaults={"is_enabled": True}
            )

@receiver(post_save, sender=School)
def create_school_features_on_school_create(sender, instance, created, **kwargs):
    """Automatically attach all system features and seed default public holidays to any newly created school."""
    for name in DEFAULT_FEATURES:
        feat, _ = Feature.objects.get_or_create(name=name.strip().lower())
        SchoolFeature.objects.get_or_create(
            school=instance,
            feature=feat,
            defaults={"is_enabled": True}
        )
    try:
        from .holiday_defaults import seed_default_school_holidays
        seed_default_school_holidays(instance)
    except Exception:
        pass


@receiver(post_save, sender=School)
def sync_school_login_credentials(sender, instance, **kwargs):
    """
    Mirror the school contact details onto the school's login user.

    Login resolves the identifier against ``CustomUser`` (email, mobile or
    username), so a ``School`` row whose email/mobile is never mirrored is
    unreachable no matter what the school form shows. Doing this in a
    ``post_save`` receiver instead of a view means every write path stays
    consistent - the admin, the API, a management command or a shell edit all
    behave identically.

    The existing ``login_id`` row is always updated, so no duplicate auth
    records appear and a replaced value stops authenticating immediately.

    Legacy rows can hold country-coded numbers (``+919876543210``). Those do not
    satisfy the 10-digit rule, so they are deliberately left alone rather than
    pushed onto the login account as an identifier that can never match.
    """
    user = getattr(instance, "login_id", None)
    if user is None:
        return

    email = (instance.email or "").strip().lower() or None
    if user.email != email:
        user.email = email
        # Saved on its own first: a mobile clash must never roll back the email.
        user.save(update_fields=["email"])

    mobile = normalize_mobile(instance.phone)
    if is_valid_mobile(mobile) and user.mobile != mobile:
        user.mobile = mobile
        try:
            user.save(update_fields=["mobile"])
        except IntegrityError:
            # Another account already owns this number, so the school cannot own
            # it too. The school edit itself is still valid and email login keeps
            # working, but this must not disappear silently - otherwise the school
            # silently loses mobile login with no visible cause.
            logger.warning(
                "School %s (%s): mobile %s is already registered to another "
                "account, so it was not mirrored onto login user %s. That user "
                "keeps their previous mobile and can no longer log in by number.",
                instance.pk, instance.name, mobile, user.pk,
            )
