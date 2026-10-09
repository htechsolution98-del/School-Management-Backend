from rest_framework.permissions import BasePermission
from .models import Student

class Is_super_admin(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        role = getattr(user, "role", "") or ""
        return bool(
            user.is_superuser
            or user.is_staff
            or role.lower() in ["superadmin", "super_admin", "super admin"]
            or user.groups.filter(name__in=["super_admin", "superadmin", "Super Admin"]).exists()
        )


class Is_admin_trustee(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        return user.groups.filter(name__in=["admin(trustee)", "trustee", "ADMIN"]).exists()


CLERK_ROLES = ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "ASSISTANTCLERK", "FEES_CLERK"]
CLERK_GROUPS = [
    "CLERK", "clerk", "Clerk",
    "ASSISTANT CLERK", "assistant clerk", "Assistant Clerk",
    "ASSISTANT_CLERK", "assistant_clerk", "Assistant_Clerk",
    "ASSISTANTCLERK", "assistantclerk",
    "fees_clerk", "FEES_CLERK",
]

class Is_super_admin(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        role = getattr(user, "role", "") or ""
        return bool(
            user.is_superuser
            or user.is_staff
            or role.lower() in ["superadmin", "super_admin", "super admin"]
            or user.groups.filter(name__in=["super_admin", "superadmin", "Super Admin"]).exists()
        )


class Is_admin_trustee(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        return user.groups.filter(name__in=["admin(trustee)", "trustee", "ADMIN"]).exists()


class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "TRUSTEE"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES:
            return True
        return user.groups.filter(name__in=CLERK_GROUPS).exists()


class IsFeeManager(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["FEES MANAGEMENT", "FEE MANAGEMENT", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "TRUSTEE"] or role in CLERK_ROLES:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["FEES MANAGEMENT", "FEE MANAGEMENT", "PRINCIPAL"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__iexact="FEES MANAGEMENT").exists()
            or user.groups.filter(name__in=["FEES MANAGEMENT", "Fee Management", "fees management", "ADMIN", "admin", "admin(trustee)", "PRINCIPAL", "principal"] + CLERK_GROUPS).exists()
        )


class Isprincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.groups.filter(name__iexact="PRINCIPAL").exists()


class Isstudent(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            user.groups.filter(name__iexact="STUDENT").exists()
            or getattr(user, "role", "").lower() == "student"
            or Student.objects.filter(user=user).exists()
        )


class Isparent(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            user.groups.filter(name__in=["PARENT", "PARENTS", "parent", "parents"]).exists()
            or getattr(user, "role", "").lower() in ["parent", "parents"]
        )


class Isteacher(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            user.groups.filter(name__iexact="TEACHER").exists()
            or getattr(user, "role", "").lower() == "teacher"
            or hasattr(user, "staff")
        )


class Isinventory(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if getattr(user, 'role', '') in ['INVENTORY', 'PRINCIPAL', 'ADMIN', 'SUPERADMIN']:
            return True
        if user.groups.filter(name__in=['INVENTORY', 'PRINCIPAL', 'super_admin']).exists():
            return True
        staff = getattr(user, 'staff', None)
        if staff and staff.category in ['INVENTORY', 'PRINCIPAL']:
            return True
        return False


class IsTempUser(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.groups.filter(name__iexact="temp_user").exists()


class HasModuleAccess(BasePermission):
    """
    Allows access if user is mapped to module
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not user.is_active:
            return False
        if user.is_superuser:
            return True
        module_code = getattr(view, "module_code", None)
        if not module_code:
            raise AttributeError("module_code is required in the view")
        from .models import UserModuleAccess
        return UserModuleAccess.objects.filter(
            user=user, module__code=module_code, module__is_active=True
        ).exists()


class IsAdminTrusteeOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return user.groups.filter(name__in=["admin(trustee)", "PRINCIPAL"]).exists()


class IsClerkOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "FEES MANAGEMENT"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=["PRINCIPAL", "admin(trustee)", "FEES MANAGEMENT", "ADMIN", "admin", "principal"] + CLERK_GROUPS).exists()
        )
        
IsClerkOrPrincipalOrAdmin = IsClerkOrPrincipal


class IsClerkOrAdmin(BasePermission):
    """
    Grants access to Clerk, Assistant Clerk, Principal, Trustee, and Admin users for HR & configurations.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "FEES MANAGEMENT"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL", "TRUSTEE", "ADMIN"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=[
                "PRINCIPAL", "principal", "Principal",
                "admin(trustee)", "trustee", "Trustee",
                "ADMIN", "admin", "Admin",
                "super_admin", "superadmin", "Super Admin",
            ] + CLERK_GROUPS).exists()
        )


class IsPrincipalOrTrustee(BasePermission):
    """Principal, Clerk, Assistant Clerk, Trustee and Admin can approve/reject leave requests."""
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=["PRINCIPAL", "admin(trustee)", "ADMIN", "admin", "principal"] + CLERK_GROUPS).exists()
        )


class IsClerkOrTrustee(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=['admin(trustee)', 'ADMIN', 'admin', 'PRINCIPAL', 'principal', 'trustee'] + CLERK_GROUPS).exists()
        )


class IsClerkOrTempUser(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        role = str(getattr(user, 'role', '') or "").strip().upper()
        if role in CLERK_ROLES or role in ['TEMP_USER', 'PRINCIPAL', 'ADMIN']:
            return True
        return user.groups.filter(name__in=['temp_user', 'PRINCIPAL', 'admin(trustee)'] + CLERK_GROUPS).exists()


class IsLibrarian(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        if getattr(user, 'role', '') in ['LIBRARIAN', 'PRINCIPAL', 'ADMIN', 'SUPERADMIN']:
            return True
        if user.groups.filter(name__in=['LIBRARIAN', 'PRINCIPAL', 'super_admin']).exists():
            return True
        staff = getattr(user, 'staff', None)
        if staff and staff.category in ['LIBRARIAN', 'PRINCIPAL']:
            return True
        return False
