from rest_framework import serializers
from .models import ActivityLog, School


class ActivityLogSerializer(serializers.ModelSerializer):
    school_name = serializers.SerializerMethodField()
    school_slug = serializers.SerializerMethodField()
    user_username = serializers.SerializerMethodField()
    user_name = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()
    module_display = serializers.CharField(source="get_module_display", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "school",
            "school_name",
            "school_slug",
            "user",
            "user_username",
            "user_name",
            "user_role",
            "module",
            "module_display",
            "action",
            "action_display",
            "title",
            "description",
            "ip_address",
            "user_agent",
            "extra_data",
            "created_at",
        ]
        read_only_fields = fields

    def _resolve_user_obj(self, obj):
        if obj.user:
            return obj.user
        if obj.user_name:
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                return User.objects.filter(username=obj.user_name).first()
            except Exception:
                pass
        return None

    def get_user_name(self, obj):
        user = self._resolve_user_obj(obj)
        if user:
            try:
                from .serializer import _user_display_name
                name = _user_display_name(user)
                if name and name != getattr(user, "username", ""):
                    return name
            except Exception:
                pass
        elif obj.user_name:
            try:
                from .models import Student
                student = Student.objects.filter(gr_no=obj.user_name).first()
                if student:
                    s_name = " ".join(part for part in [student.name, student.father_name, student.surname] if part).strip()
                    if s_name:
                        return s_name
            except Exception:
                pass
        return obj.user_name or (obj.user.username if obj.user else "System")

    def get_title(self, obj):
        display_name = self.get_user_name(obj)
        role = (obj.user_role or "User").title()
        raw_title = obj.title or ""
        username = obj.user.username if obj.user else (obj.user_name or "")
        
        # If raw title contains raw username with (student) or (parent) or role, polish it with real name
        if username and (
            f"{username.lower()} (student)" in raw_title.lower()
            or f"{username.lower()} (parent)" in raw_title.lower()
            or f"{username.lower()} signed in" in raw_title.lower()
            or f"{username.lower()} signed out" in raw_title.lower()
        ):
            if obj.action == "LOGIN":
                return f"{display_name} ({role}) Signed In"
            elif obj.action == "LOGOUT":
                return f"{display_name} ({role}) Signed Out"
            return f"{display_name} ({role}) - {obj.action.title()}"
        return raw_title

    def get_description(self, obj):
        raw_desc = obj.description or ""
        display_name = self.get_user_name(obj)
        username = obj.user.username if obj.user else (obj.user_name or "")
        if username and display_name and display_name != username:
            # e.g., "User 101 logged into the system." -> "User 101 (asdf asdfg asd) logged into the system."
            if f"User {username} logged into" in raw_desc:
                return f"User {display_name} ({username}) logged into the system."
            if f"User {username} logged out" in raw_desc:
                return f"User {display_name} ({username}) logged out of the system."
        return raw_desc

    def get_school_name(self, obj):
        if obj.school:
            return obj.school.name
        user = self._resolve_user_obj(obj)
        if user:
            if getattr(user, "school", None):
                return user.school.name
            try:
                from .models import Student, Perents
                student = Student.objects.filter(user=user).select_related("school").first()
                if not student and getattr(user, "username", None):
                    student = Student.objects.filter(gr_no=user.username).select_related("school").first()
                if student and student.school:
                    return student.school.name
                parent = Perents.objects.filter(user=user).select_related("perents_of__school").first()
                if parent and parent.perents_of and parent.perents_of.school:
                    return parent.perents_of.school.name
            except Exception:
                pass
        elif obj.user_name:
            try:
                from .models import Student
                student = Student.objects.filter(gr_no=obj.user_name).select_related("school").first()
                if student and student.school:
                    return student.school.name
            except Exception:
                pass
        return "Global / Multi-School"

    def get_school_slug(self, obj):
        if obj.school:
            return obj.school.slug
        return "global"

    def get_user_username(self, obj):
        return obj.user.username if obj.user else (obj.user_name or "system")

