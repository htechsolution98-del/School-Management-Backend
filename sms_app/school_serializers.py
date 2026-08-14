from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import *

User = get_user_model()

class FeatureSerialzer(serializers.ModelSerializer):
    class Meta:
        model = Feature
        fields = "__all__"


# -----------FOR SET WHICH FEATURE SCHOOL HAS-----------


class SchoolFeatureSerializer(serializers.ModelSerializer):
    feature_name = serializers.CharField(source="feature.name", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "school", "feature", "feature_name", "is_enabled"]
        read_only_fields = ["is_enabled", "feature_name"]

    def validate(self, data):
        school = data.get("school")
        feature = data.get("feature")

        if SchoolFeature.objects.filter(school=school, feature=feature).exists():
            raise serializers.ValidationError(
                {"message": "This Feature already have to this school"}
            )
        return data


# -----------TO GET FEATURE FRO DROP DOWN IN STAFF CREATE---------------


class GetFeatureSerializer(serializers.ModelSerializer):

    feature_name = serializers.CharField(source="feature.name", read_only=True)
    feature_id = serializers.CharField(source="feature.id", read_only=True)

    class Meta:
        model = SchoolFeature
        fields = ["id", "feature_id", "feature_name"]


from rest_framework import serializers




class ChangeFeatureStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolFeature
        fields = ["is_enabled"]




class SchoolSerializer(serializers.ModelSerializer):
    feature_ids = serializers.PrimaryKeyRelatedField(
        queryset=Feature.objects.all(), many=True, write_only=True
    )
    school_features = SchoolFeatureSerializer(
        source="schoolfeature_set", many=True, read_only=True
    )

    class Meta:
        model = School
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "slug",
            "code",
            "feature_ids",
            "address",
            "city",
            "state",
            "country",
            "pincode",
            "logo",
            "index_no",
            "is_active",
            "school_features",
        ]
        read_only_fields = ["slug", "login_id"]

    def validate(self, data):
        email = data.get("email")
        if email:
            qs = User.objects.filter(email=email)
            if self.instance and getattr(self.instance, "login_id", None):
                qs = qs.exclude(id=self.instance.login_id.id)
            if qs.exists():
                raise serializers.ValidationError({"message": "Email is already exists."})
        return data

    def validate_feature_ids(self, value):
        ids = [f.id for f in value]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError("Duplicate features are not allowed.")

        return value




class SchoolListSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "logo", "index_no"]




