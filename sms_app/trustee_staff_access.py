"""Read-only Trustee policy shared by reporting and existing HR routes."""
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from .models import UserModuleAccess
from .trustee_inventory_report import IsTrustee


def can_view_salary(user):
    return user.has_perm('sms_app.view_staffsalarypayment') or UserModuleAccess.objects.filter(
        user=user, module__is_active=True, module__code__in=['PAYROLL', 'STAFF_SALARY', 'SALARY']
    ).exists()


def can_view_contacts(user):
    return user.has_perm('sms_app.view_staff')


class TrusteeStaffReadOnlyMixin:
    """Runs independently of action-specific permissions, after authentication."""
    trustee_salary_resource = False
    trustee_report_only = False

    def check_permissions(self, request):
        if IsTrustee().has_permission(request, self):
            if request.method not in SAFE_METHODS:
                raise PermissionDenied('Trustee staff access is read-only. Changes and approvals are not permitted.')
            if self.trustee_report_only:
                raise PermissionDenied('Use the permission-filtered Trustee Staff Management report.')
            if self.trustee_salary_resource and not can_view_salary(request.user):
                raise PermissionDenied('An explicit salary report permission is required.')
        return super().check_permissions(request)
