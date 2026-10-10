import logging
from typing import Any, Optional
from django.utils import timezone
from .models import ActivityLog, School, CustomUser

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> str:
    """Extract client IP address from request headers."""
    if not request:
        return ""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "")
    return ip or ""


def _get_user_agent(request) -> str:
    """Extract browser user agent from request."""
    if not request:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:255]


def _resolve_user_display_name(user) -> str:
    """Resolve human readable name for user."""
    if not user:
        return "System"
    try:
        from .serializer import _user_display_name
        return _user_display_name(user)
    except Exception:
        full_name = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
        if full_name:
            return full_name
        return getattr(user, "username", "Unknown User")


def _resolve_user_role(user) -> str:
    """Resolve role for user."""
    if not user:
        return "SYSTEM"
    if getattr(user, "is_superuser", False):
        return "SUPERADMIN"
    
    roles = list(user.groups.values_list("name", flat=True)) if hasattr(user, "groups") else []
    if roles:
        return roles[0].title()
    
    user_role = str(getattr(user, "role", "") or "").strip()
    if user_role:
        return user_role.title()
    
    try:
        from .models import Student, Perents, Staff
        if Student.objects.filter(user=user).exists() or Student.objects.filter(gr_no=getattr(user, "username", "")).exists():
            return "Student"
        if Perents.objects.filter(user=user).exists():
            return "Parent"
        if Staff.objects.filter(user=user).exists():
            return "Staff"
    except Exception:
        pass

    return "User"


def log_activity(
    user: Optional[Any] = None,
    action: str = "OTHER",
    module: str = "OTHER",
    title: str = "",
    description: str = "",
    school: Optional[Any] = None,
    extra_data: Optional[dict] = None,
    request: Optional[Any] = None,
) -> Optional[ActivityLog]:
    """
    Central logging function to record any user or system action across all modules.
    Safe against exceptions so it never disrupts ongoing business transactions.
    """
    try:
        # If user not passed, resolve from request
        if not user and request and hasattr(request, "user") and request.user.is_authenticated:
            user = request.user

        # Resolve school
        resolved_school = school
        if not resolved_school and user:
            resolved_school = getattr(user, "school", None)
            if not resolved_school:
                resolved_school = getattr(user, "managed_school", None)
            if not resolved_school:
                try:
                    from .models import Student, Perents
                    student = Student.objects.filter(user=user).select_related("school").first()
                    if not student and getattr(user, "username", None):
                        student = Student.objects.filter(gr_no=user.username).select_related("school").first()
                    if student and student.school:
                        resolved_school = student.school
                    else:
                        parent = Perents.objects.filter(user=user).select_related("perents_of__school").first()
                        if parent and parent.perents_of and parent.perents_of.school:
                            resolved_school = parent.perents_of.school
                except Exception:
                    pass

        ip = _get_client_ip(request)
        ua = _get_user_agent(request)
        user_name = _resolve_user_display_name(user)
        user_role = _resolve_user_role(user)

        log_entry = ActivityLog.objects.create(
            school=resolved_school,
            user=user if isinstance(user, CustomUser) else None,
            user_name=user_name,
            user_role=user_role,
            module=module.upper(),
            action=action.upper(),
            title=title or f"{user_name} ({user_role}) performed {action}",
            description=description or "",
            ip_address=ip,
            user_agent=ua,
            extra_data=extra_data or {},
        )
        return log_entry
    except Exception as e:
        logger.warning(f"Failed to record ActivityLog: {e}")
        return None
