from rest_framework import serializers
from .tutorial_models import PageTutorial


class PageTutorialSerializer(serializers.ModelSerializer):
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PageTutorial
        fields = [
            'id',
            'role',
            'route_path',
            'title',
            'summary',
            'steps',
            'dummy_data',
            'video_url',
            'tips',
            'created_at',
            'updated_at',
            'updated_by',
            'updated_by_name',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'updated_by', 'updated_by_name']

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            first = obj.updated_by.first_name or ""
            last = obj.updated_by.last_name or ""
            full = f"{first} {last}".strip()
            return full or obj.updated_by.username
        return None

    def validate_route_path(self, value):
        normalized = value.strip().rstrip('/')
        if not normalized.startswith('/'):
            normalized = '/' + normalized
        return normalized
