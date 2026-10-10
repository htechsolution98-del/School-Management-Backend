import mimetypes
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError

from .support_models import SupportTicket, TicketMessage
from .support_serializers import (
    SupportTicketSerializer,
    TicketMessageSerializer,
    count_words,
    MAX_WORDS_LIMIT,
    MAX_MEDIA_BYTES,
)
from .serializer import _user_display_name
from .models import School, Student, Perents, Staff


class IsSuperAdminUser(permissions.BasePermission):
    """Allows access only to super admin users."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_superuser or user.groups.filter(name="super_admin").exists())


class SupportTicketViewSet(viewsets.ModelViewSet):
    serializer_class = SupportTicketSerializer
    permission_classes = [permissions.IsAuthenticated]

    def _is_super_admin(self, user):
        return bool(user.is_superuser or user.groups.filter(name="super_admin").exists())

    def _resolve_user_role(self, user):
        roles = list(user.groups.values_list("name", flat=True))
        if user.is_superuser:
            return "SUPER_ADMIN"
        if "trustee" in roles:
            return "TRUSTEE"
        if "principal" in roles:
            return "PRINCIPAL"
        if "clerk" in roles:
            return "CLERK"
        if "teacher" in roles:
            return "TEACHER"
        if "accountant" in roles or "finance" in roles:
            return "FEES_MANAGEMENT"
        if "inventory" in roles:
            return "INVENTORY"
        if roles:
            return roles[0].upper()
        if user.role:
            return str(user.role).upper()
        return "STAFF"

    def _resolve_user_school(self, user):
        if getattr(user, "school", None):
            return user.school
        if getattr(user, "managed_school", None):
            return user.managed_school
        try:
            staff = Staff.objects.filter(user=user).select_related("school").first()
            if staff and staff.school:
                return staff.school
            student = Student.objects.filter(user=user).select_related("school").first()
            if student and student.school:
                return student.school
            parent = Perents.objects.filter(user=user).select_related("perents_of__school").first()
            if parent and parent.perents_of and parent.perents_of.school:
                return parent.perents_of.school
        except Exception:
            pass
        return None

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return SupportTicket.objects.none()

        qs = SupportTicket.objects.select_related("created_by", "school", "accepted_by", "closed_by").prefetch_related("messages")

        if self._is_super_admin(user):
            # Super admin can see all tickets, with optional filtering
            school_id = self.request.query_params.get("school_id")
            if school_id and school_id != "ALL":
                qs = qs.filter(school_id=school_id)
        else:
            # School users can only see their own tickets
            qs = qs.filter(created_by=user)

        # Filters
        ticket_status = self.request.query_params.get("status")
        if ticket_status and ticket_status != "ALL":
            qs = qs.filter(status=ticket_status)

        priority = self.request.query_params.get("priority")
        if priority and priority != "ALL":
            qs = qs.filter(priority=priority)

        category = self.request.query_params.get("category")
        if category and category != "ALL":
            qs = qs.filter(category=category)

        role = self.request.query_params.get("role")
        if role and role != "ALL":
            qs = qs.filter(requester_role__iexact=role)

        search = self.request.query_params.get("search")
        if search:
            search = search.strip()
            qs = qs.filter(
                Q(ticket_number__icontains=search)
                | Q(subject__icontains=search)
                | Q(description__icontains=search)
                | Q(requester_name__icontains=search)
                | Q(school__name__icontains=search)
            )

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        role = self._resolve_user_role(user)
        name = _user_display_name(user)
        school = self._resolve_user_school(user)

        with transaction.atomic():
            ticket = serializer.save(
                created_by=user,
                requester_role=role,
                requester_name=name,
                school=school,
                status="PENDING",
            )
            # Create initial message in the chat thread
            TicketMessage.objects.create(
                ticket=ticket,
                sender=user,
                sender_name=name,
                sender_role=role,
                message_type="TEXT",
                text_content=ticket.description,
            )

    @action(detail=False, methods=["get"], url_path="active")
    def active_ticket(self, request):
        """Returns the user's active ticket if one exists."""
        user = request.user
        active = SupportTicket.objects.filter(
            created_by=user,
            status__in=["PENDING", "IN_PROGRESS"],
        ).order_by("-created_at").first()

        if active:
            serializer = self.get_serializer(active)
            return Response({"has_active_ticket": True, "ticket": serializer.data})
        return Response({"has_active_ticket": False, "ticket": None})

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Returns summary counts of tickets."""
        user = request.user
        is_super = self._is_super_admin(user)
        base_qs = SupportTicket.objects.all() if is_super else SupportTicket.objects.filter(created_by=user)

        total_count = base_qs.count()
        pending_count = base_qs.filter(status="PENDING").count()
        in_progress_count = base_qs.filter(status="IN_PROGRESS").count()
        closed_count = base_qs.filter(status="CLOSED").count()

        schools_data = []
        if is_super:
            schools = School.objects.all().values("id", "name", "slug")
            schools_data = list(schools)

        return Response({
            "total_count": total_count,
            "pending_count": pending_count,
            "in_progress_count": in_progress_count,
            "closed_count": closed_count,
            "is_super_admin": is_super,
            "schools": schools_data,
        })

    @action(detail=True, methods=["post"], url_path="accept", permission_classes=[IsSuperAdminUser])
    def accept_ticket(self, request, pk=None):
        """Super Admin accepts a pending ticket to open live chat."""
        ticket = self.get_object()
        if ticket.status == "CLOSED":
            return Response(
                {"error": "This ticket has already been closed and cannot be re-accepted."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            ticket.status = "IN_PROGRESS"
            ticket.accepted_by = request.user
            ticket.accepted_at = timezone.now()
            ticket.save(update_fields=["status", "accepted_by", "accepted_at", "updated_at"])

            admin_name = _user_display_name(request.user)
            TicketMessage.objects.create(
                ticket=ticket,
                sender=request.user,
                sender_name=admin_name,
                sender_role="SUPER_ADMIN",
                message_type="SYSTEM",
                text_content=f"Ticket accepted by Super Admin {admin_name}. Live chat is now open.",
            )

        serializer = self.get_serializer(ticket)
        return Response({
            "message": "Ticket accepted successfully. Chat is now open.",
            "ticket": serializer.data,
        })

    @action(detail=True, methods=["post"], url_path="close", permission_classes=[IsSuperAdminUser])
    def close_ticket(self, request, pk=None):
        """Super Admin closes the ticket and ends live chat."""
        ticket = self.get_object()
        if ticket.status == "CLOSED":
            return Response(
                {"error": "This ticket is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        notes = request.data.get("closing_notes", "").strip()

        with transaction.atomic():
            ticket.status = "CLOSED"
            ticket.closed_by = request.user
            ticket.closed_at = timezone.now()
            ticket.closing_notes = notes or None
            ticket.save(update_fields=["status", "closed_by", "closed_at", "closing_notes", "updated_at"])

            admin_name = _user_display_name(request.user)
            close_text = f"Ticket closed by Super Admin {admin_name}."
            if notes:
                close_text += f" Resolution: {notes}"

            TicketMessage.objects.create(
                ticket=ticket,
                sender=request.user,
                sender_name=admin_name,
                sender_role="SUPER_ADMIN",
                message_type="SYSTEM",
                text_content=close_text,
            )

        serializer = self.get_serializer(ticket)
        return Response({
            "message": "Ticket closed successfully.",
            "ticket": serializer.data,
        })

    @action(detail=True, methods=["get", "post"], url_path="messages")
    def ticket_messages(self, request, pk=None):
        """List or send messages for a specific support ticket."""
        ticket = self.get_object()
        user = request.user
        is_super = self._is_super_admin(user)

        # Check access permission
        if not is_super and ticket.created_by != user:
            raise PermissionDenied("You do not have permission to view or participate in this ticket.")

        if request.method == "GET":
            messages = ticket.messages.all().order_by("created_at")
            serializer = TicketMessageSerializer(messages, many=True, context={"request": request})
            return Response({
                "ticket_id": ticket.id,
                "ticket_number": ticket.ticket_number,
                "ticket_status": ticket.status,
                "subject": ticket.subject,
                "messages": serializer.data,
            })

        elif request.method == "POST":
            if ticket.status == "CLOSED":
                return Response(
                    {"error": "This ticket is closed. No further messages can be sent."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # If pending and user is not superadmin, they can still post notes or info
            text = (request.data.get("text_content") or "").strip()
            media = request.FILES.get("media_file")

            if not text and not media:
                return Response(
                    {"error": "Please provide a text message or attach a file."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Strict word limit validation
            if text:
                words = count_words(text)
                if words > MAX_WORDS_LIMIT:
                    return Response(
                        {"error": f"Message text exceeds the {MAX_WORDS_LIMIT} words limit ({words} words entered)."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Strict media size validation (200 KB)
            media_size = 0
            media_name = None
            media_type = None
            if media:
                if media.size > MAX_MEDIA_BYTES:
                    size_kb = round(media.size / 1024, 1)
                    return Response(
                        {"error": f"Attached media exceeds the 200 KB limit (file size: {size_kb} KB). Please choose a file smaller than 200 KB."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                media_size = media.size
                media_name = media.name
                media_type = media.content_type or mimetypes.guess_type(media.name)[0] or "application/octet-stream"

            sender_name = _user_display_name(user)
            sender_role = "SUPER_ADMIN" if is_super else self._resolve_user_role(user)
            msg_type = "MEDIA" if media else "TEXT"

            with transaction.atomic():
                msg = TicketMessage.objects.create(
                    ticket=ticket,
                    sender=user,
                    sender_name=sender_name,
                    sender_role=sender_role,
                    message_type=msg_type,
                    text_content=text or None,
                    media_file=media,
                    media_name=media_name,
                    media_size_bytes=media_size,
                    media_content_type=media_type,
                )
                ticket.updated_at = timezone.now()
                ticket.save(update_fields=["updated_at"])

            serializer = TicketMessageSerializer(msg, context={"request": request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)
