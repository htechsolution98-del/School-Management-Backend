from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import School, Feature, SchoolFeature

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
        feat, _ = Feature.objects.get_or_create(name=name)
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
    """Automatically attach all system features to any newly created school."""
    for name in DEFAULT_FEATURES:
        feat, _ = Feature.objects.get_or_create(name=name)
        SchoolFeature.objects.get_or_create(
            school=instance,
            feature=feat,
            defaults={"is_enabled": True}
        )
