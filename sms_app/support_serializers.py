from rest_framework import serializers
from .support_models import SupportTicket, TicketMessage
from .serializer import _user_display_name
from .models import School


MAX_WORDS_LIMIT = 200
MAX_MEDIA_BYTES = 200 * 1024  # 200 KB


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(text.strip().split())


class TicketMessageSerializer(serializers.ModelSerializer):
    sender_display_name = serializers.SerializerMethodField()
    is_super_admin_sender = serializers.SerializerMethodField()
    media_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = [
            "id",
            "ticket",
            "sender",
            "sender_name",
            "sender_display_name",
            "sender_role",
            "is_super_admin_sender",
            "message_type",
            "text_content",
            "media_file",
            "media_url",
            "media_name",
            "media_size_bytes",
            "media_content_type",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "ticket",
            "sender",
            "sender_name",
            "sender_role",
            "is_super_admin_sender",
            "media_url",
            "media_size_bytes",
            "media_content_type",
            "created_at",
        ]

    def get_sender_display_name(self, obj):
        if obj.sender:
            return _user_display_name(obj.sender)
        return obj.sender_name or "System"

    def get_is_super_admin_sender(self, obj):
        if not obj.sender:
            return False
        if obj.sender.is_superuser or "super_admin" in (obj.sender_role or "").lower():
            return True
        return False

    def get_media_url(self, obj):
        if obj.media_file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.media_file.url)
            return obj.media_file.url
        return None

    def validate(self, attrs):
        text = attrs.get("text_content") or ""
        media = attrs.get("media_file")

        if not text.strip() and not media:
            raise serializers.ValidationError("Either a text message or a media file is required.")

        if text.strip():
            words = count_words(text)
            if words > MAX_WORDS_LIMIT:
                raise serializers.ValidationError(
                    {"text_content": f"Message text exceeds the {MAX_WORDS_LIMIT} words limit ({words} words entered)."}
                )

        if media:
            if media.size > MAX_MEDIA_BYTES:
                size_kb = round(media.size / 1024, 1)
                raise serializers.ValidationError(
                    {"media_file": f"Attached media exceeds the 200 KB limit (file size: {size_kb} KB)."}
                )

        return attrs


class SupportTicketSerializer(serializers.ModelSerializer):
    school_name = serializers.SerializerMethodField()
    creator_display_name = serializers.SerializerMethodField()
    accepted_by_name = serializers.SerializerMethodField()
    closed_by_name = serializers.SerializerMethodField()
    unread_messages_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    priority_display = serializers.CharField(source="get_priority_display", read_only=True)
    category_display = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "ticket_number",
            "school",
            "school_name",
            "created_by",
            "creator_display_name",
            "requester_role",
            "requester_name",
            "subject",
            "description",
            "category",
            "category_display",
            "priority",
            "priority_display",
            "status",
            "status_display",
            "accepted_by",
            "accepted_by_name",
            "accepted_at",
            "closed_by",
            "closed_by_name",
            "closed_at",
            "closing_notes",
            "unread_messages_count",
            "last_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "ticket_number",
            "school",
            "created_by",
            "creator_display_name",
            "requester_role",
            "requester_name",
            "status",
            "status_display",
            "accepted_by",
            "accepted_by_name",
            "accepted_at",
            "closed_by",
            "closed_by_name",
            "closed_at",
            "closing_notes",
            "unread_messages_count",
            "last_message",
            "created_at",
            "updated_at",
        ]

    def get_school_name(self, obj):
        if obj.school:
            return obj.school.name
        if obj.created_by and getattr(obj.created_by, "school", None):
            return obj.created_by.school.name
        return "Global / Enterprise"

    def get_creator_display_name(self, obj):
        if obj.created_by:
            return _user_display_name(obj.created_by)
        return obj.requester_name or "Unknown Requester"

    def get_accepted_by_name(self, obj):
        if obj.accepted_by:
            return _user_display_name(obj.accepted_by)
        return None

    def get_closed_by_name(self, obj):
        if obj.closed_by:
            return _user_display_name(obj.closed_by)
        return None

    def get_unread_messages_count(self, obj):
        return 0

    def get_last_message(self, obj):
        last_msg = obj.messages.order_by("-created_at").first()
        if last_msg:
            return {
                "id": last_msg.id,
                "sender_name": last_msg.sender_name,
                "message_type": last_msg.message_type,
                "text_content": (last_msg.text_content[:80] + "...") if last_msg.text_content and len(last_msg.text_content) > 80 else last_msg.text_content,
                "created_at": last_msg.created_at,
            }
        return None

    def validate_description(self, value):
        if value:
            words = count_words(value)
            if words > MAX_WORDS_LIMIT:
                raise serializers.ValidationError(
                    f"Ticket description cannot exceed {MAX_WORDS_LIMIT} words ({words} words entered)."
                )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.user and not self.instance:
            user = request.user
            # Check 1 single active ticket restriction for non-superadmins
            is_super_admin = user.is_superuser or user.groups.filter(name="super_admin").exists()
            if not is_super_admin:
                active_ticket = SupportTicket.objects.filter(
                    created_by=user,
                    status__in=["PENDING", "IN_PROGRESS"],
                ).first()
                if active_ticket:
                    raise serializers.ValidationError(
                        {
                            "error": "active_ticket_exists",
                            "message": f"You already have an active support ticket (#{active_ticket.ticket_number} - {active_ticket.subject}). You can raise a new ticket once this one is closed.",
                            "active_ticket_id": active_ticket.id,
                            "active_ticket_number": active_ticket.ticket_number,
                        }
                    )
        return attrs
