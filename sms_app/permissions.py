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


class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["CLERK", "ASSISTANT CLERK", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["CLERK", "ASSISTANT CLERK"]:
            return True
        return (
            user.groups.filter(name__iexact="CLERK").exists()
            or user.groups.filter(name__iexact="ASSISTANT CLERK").exists()
            or user.groups.filter(name__in=["CLERK", "clerk", "Clerk", "ASSISTANT CLERK", "assistant clerk", "Assistant Clerk"]).exists()
        )


class IsFeeManager(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["FEES MANAGEMENT", "FEE MANAGEMENT", "CLERK", "ASSISTANT CLERK", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["FEES MANAGEMENT", "FEE MANAGEMENT", "CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return (
            user.groups.filter(name__iexact="FEES MANAGEMENT").exists()
            or user.groups.filter(name__in=["FEES MANAGEMENT", "Fee Management", "fees management", "CLERK", "clerk", "Clerk", "ASSISTANT CLERK", "assistant clerk", "ADMIN", "admin", "admin(trustee)", "PRINCIPAL", "principal", "VICE PRINCIPAL", "vice principal"]).exists()
        )


class Isprincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["PRINCIPAL", "VICE PRINCIPAL", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "TRUSTEE"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return (
            user.groups.filter(name__iexact="PRINCIPAL").exists()
            or user.groups.filter(name__iexact="VICE PRINCIPAL").exists()
            or user.groups.filter(name__in=["PRINCIPAL", "principal", "Principal", "VICE PRINCIPAL", "vice principal", "Vice Principal"]).exists()
        )


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
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["ADMIN(TRUSTEE)", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return user.groups.filter(name__in=["admin(trustee)", "trustee", "PRINCIPAL", "principal", "VICE PRINCIPAL", "vice principal"]).exists()


class IsClerkOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "FEES MANAGEMENT"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return (
            user.groups.filter(name__iexact="CLERK").exists()
            or user.groups.filter(name__iexact="ASSISTANT CLERK").exists()
            or user.groups.filter(name__in=["CLERK", "clerk", "Clerk", "ASSISTANT CLERK", "assistant clerk", "Assistant Clerk", "PRINCIPAL", "principal", "Principal", "VICE PRINCIPAL", "vice principal", "Vice Principal", "admin(trustee)", "FEES MANAGEMENT", "ADMIN", "admin"]).exists()
        )
        
IsClerkOrPrincipalOrAdmin = IsClerkOrPrincipal


class IsClerkOrAdmin(BasePermission):
    """
    Grants access to Clerk, Principal, Trustee, and Admin users for HR & configurations.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "FEES MANAGEMENT"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN"]:
            return True
        return (
            user.groups.filter(name__iexact="CLERK").exists()
            or user.groups.filter(name__iexact="ASSISTANT CLERK").exists()
            or user.groups.filter(name__in=[
                "CLERK", "clerk", "Clerk",
                "ASSISTANT CLERK", "assistant clerk", "Assistant Clerk",
                "PRINCIPAL", "principal", "Principal",
                "VICE PRINCIPAL", "vice principal", "Vice Principal",
                "admin(trustee)", "trustee", "Trustee",
                "ADMIN", "admin", "Admin",
                "super_admin", "superadmin", "Super Admin",
            ]).exists()
        )


class IsPrincipalOrTrustee(BasePermission):
    """Principal, Clerk, Trustee and Admin can approve/reject leave requests."""
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return (
            user.groups.filter(name__iexact="CLERK").exists()
            or user.groups.filter(name__iexact="ASSISTANT CLERK").exists()
            or user.groups.filter(name__in=["CLERK", "clerk", "Clerk", "ASSISTANT CLERK", "assistant clerk", "Assistant Clerk", "PRINCIPAL", "principal", "Principal", "VICE PRINCIPAL", "vice principal", "Vice Principal", "admin(trustee)", "ADMIN", "admin"]).exists()
        )


class IsClerkOrTrustee(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["CLERK", "ASSISTANT CLERK", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["CLERK", "ASSISTANT CLERK", "PRINCIPAL", "VICE PRINCIPAL"]:
            return True
        return (
            user.groups.filter(name__iexact="CLERK").exists()
            or user.groups.filter(name__iexact="ASSISTANT CLERK").exists()
            or user.groups.filter(name__in=['CLERK', 'clerk', 'Clerk', 'ASSISTANT CLERK', 'assistant clerk', 'Assistant Clerk', 'admin(trustee)', 'ADMIN', 'admin', 'PRINCIPAL', 'principal', 'Principal', 'VICE PRINCIPAL', 'vice principal', 'Vice Principal', 'trustee']).exists()
        )


class IsClerkOrTempUser(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, 'role', '') or "").strip().upper()
        if role in ['CLERK', 'ASSISTANT CLERK', 'temp_user', 'PRINCIPAL', 'VICE PRINCIPAL', 'ADMIN', 'SUPERADMIN']:
            return True
        return user.groups.filter(name__in=['CLERK', 'clerk', 'ASSISTANT CLERK', 'assistant clerk', 'temp_user', 'PRINCIPAL', 'principal', 'VICE PRINCIPAL', 'vice principal', 'admin(trustee)']).exists()


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
