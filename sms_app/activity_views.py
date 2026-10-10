import datetime
from django.db.models import Q, Count
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import ActivityLog, School
from .activity_serializers import ActivityLogSerializer


class ActivityLogPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for Activity Logs:
    - Super Admin: sees activity logs across ALL schools (with school filtering).
    - Trustee / Principal / Clerk / Management: sees all activity logs for their entire school.
    - Other staff: sees their own activity logs.
    """
    serializer_class = ActivityLogSerializer
    pagination_class = ActivityLogPagination
    permission_classes = [permissions.IsAuthenticated]

    def _is_super_admin(self, user):
        role = str(getattr(user, "role", "") or "").upper()
        return bool(
            user.is_superuser
            or getattr(user, "is_staff", False)
            or "SUPER" in role
            or role in ["SUPERADMIN", "SUPER_ADMIN", "ADMIN"]
            or user.groups.filter(name__icontains="super").exists()
            or user.groups.filter(name__iexact="admin").exists()
        )

    def _is_school_management(self, user):
        role = str(getattr(user, "role", "") or "").upper()
        return bool(
            self._is_super_admin(user)
            or "TRUSTEE" in role
            or "PRINCIPAL" in role
            or "CLERK" in role
            or user.groups.filter(name__icontains="trustee").exists()
            or user.groups.filter(name__icontains="principal").exists()
            or user.groups.filter(name__icontains="clerk").exists()
        )

    def _is_trustee(self, user):
        role = str(getattr(user, "role", "") or "").upper()
        return bool(
            "TRUSTEE" in role
            or role in ["ADMIN(TRUSTEE)", "TRUSTEE"]
            or user.groups.filter(name__icontains="trustee").exists()
        )

    def get_queryset(self):
        user = self.request.user
        qs = ActivityLog.objects.select_related("school", "user").all()

        is_super = self._is_super_admin(user)
        is_trustee = self._is_trustee(user)
        school = getattr(user, "school", None) or getattr(user, "managed_school", None)

        if is_super:
            # Super Admin sees all schools but not their own logs
            qs = qs.exclude(user=user).exclude(user_name__iexact=user.username)
        elif is_trustee:
            # Trustee sees whole school logs, but NOT Super Admin logs and NOT their own logs
            if school:
                qs = (
                    qs.filter(school=school)
                    .exclude(user=user)
                    .exclude(user_name__iexact=user.username)
                    .exclude(user_role__icontains="super")
                )
            else:
                qs = qs.none()
        else:
            # Principal, Clerk, and other school staff/users:
            # CANNOT see Super Admin logs, and CANNOT see Trustee logs
            if self._is_school_management(user):
                if school:
                    qs = (
                        qs.filter(school=school)
                        .exclude(user_role__icontains="super")
                        .exclude(user_role__icontains="trustee")
                    )
                else:
                    qs = (
                        qs.filter(user=user)
                        .exclude(user_role__icontains="super")
                        .exclude(user_role__icontains="trustee")
                    )
            else:
                # Regular user sees only their own activity logs
                qs = (
                    qs.filter(user=user)
                    .exclude(user_role__icontains="super")
                    .exclude(user_role__icontains="trustee")
                )

        # Query Filters
        school_id = self.request.query_params.get("school_id")
        if school_id and school_id != "ALL" and str(school_id).lower() != "all":
            if is_super or (school and str(school.id) == str(school_id)):
                qs = qs.filter(school_id=school_id)

        module = self.request.query_params.get("module")
        if module and module != "ALL":
            qs = qs.filter(module__iexact=module)

        action_param = self.request.query_params.get("action")
        if action_param and action_param != "ALL":
            qs = qs.filter(action__iexact=action_param)

        role = self.request.query_params.get("role")
        if role and role != "ALL":
            qs = qs.filter(user_role__icontains=role)

        search = self.request.query_params.get("search")
        if search:
            s = search.strip()
            qs = qs.filter(
                Q(title__icontains=s)
                | Q(description__icontains=s)
                | Q(user_name__icontains=s)
                | Q(user_role__icontains=s)
                | Q(ip_address__icontains=s)
            )

        start_date = self.request.query_params.get("start_date")
        if start_date:
            try:
                sd = datetime.date.fromisoformat(start_date)
                qs = qs.filter(created_at__date__gte=sd)
            except Exception:
                pass

        end_date = self.request.query_params.get("end_date")
        if end_date:
            try:
                ed = datetime.date.fromisoformat(end_date)
                qs = qs.filter(created_at__date__lte=ed)
            except Exception:
                pass

        return qs.order_by("-created_at")

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Aggregate stats for the activity dashboard header."""
        user = request.user
        base_qs = ActivityLog.objects.all()

        is_super = self._is_super_admin(user)
        is_trustee = self._is_trustee(user)
        school = getattr(user, "school", None) or getattr(user, "managed_school", None)

        if is_super:
            base_qs = base_qs.exclude(user=user).exclude(user_name__iexact=user.username)
            school_id = request.query_params.get("school_id")
            if school_id and school_id != "ALL" and str(school_id).lower() != "all":
                base_qs = base_qs.filter(school_id=school_id)
        elif is_trustee:
            if school:
                base_qs = (
                    base_qs.filter(school=school)
                    .exclude(user=user)
                    .exclude(user_name__iexact=user.username)
                    .exclude(user_role__icontains="super")
                )
            else:
                base_qs = base_qs.none()
        else:
            if self._is_school_management(user) and school:
                base_qs = (
                    base_qs.filter(school=school)
                    .exclude(user_role__icontains="super")
                    .exclude(user_role__icontains="trustee")
                )
            else:
                base_qs = (
                    base_qs.filter(user=user)
                    .exclude(user_role__icontains="super")
                    .exclude(user_role__icontains="trustee")
                )

        today = timezone.localdate()
        total_count = base_qs.count()
        today_count = base_qs.filter(created_at__date=today).count()
        login_count = base_qs.filter(action="LOGIN").count()
        password_changes_count = base_qs.filter(action="PASSWORD_CHANGE").count()
        modifications_count = base_qs.filter(action__in=["CREATE", "UPDATE", "DELETE", "PUBLISH", "PAYMENT"]).count()

        # Module distribution
        module_counts = (
            base_qs.values("module")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        # Schools list for super admin filter dropdown
        schools_list = []
        if is_super:
            schools_list = list(School.objects.values("id", "name", "slug").order_by("name"))

        return Response({
            "total_count": total_count,
            "today_count": today_count,
            "login_count": login_count,
            "password_changes_count": password_changes_count,
            "modifications_count": modifications_count,
            "module_counts": list(module_counts),
            "is_super_admin": is_super,
            "schools": schools_list,
        })
