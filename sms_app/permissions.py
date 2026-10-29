from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Student, Staff

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
        from .models import Perents
        return (
            user.groups.filter(name__in=["PARENT", "PARENTS", "parent", "parents"]).exists()
            or getattr(user, "role", "").lower() in ["parent", "parents"]
            or Perents.objects.filter(user=user).exists()
        )


class IsStudentOrParent(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return (
            Isstudent().has_permission(request, view)
            or Isparent().has_permission(request, view)
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
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, 'role', '') or '').strip().upper()
        if role in ['INVENTORY', 'PRINCIPAL', 'ADMIN', 'SUPERADMIN', 'TRUSTEE', 'FEES MANAGEMENT', 'FEE MANAGEMENT', 'FEES_MANAGEMENT', 'ACCOUNTANT'] + CLERK_ROLES:
            return True
        if (
            user.groups.filter(name__iexact='INVENTORY').exists()
            or user.groups.filter(name__iexact='PRINCIPAL').exists()
            or user.groups.filter(name__iexact='super_admin').exists()
            or user.groups.filter(name__iexact='trustee').exists()
            or user.groups.filter(name__in=['FEES MANAGEMENT', 'Fee Management', 'fees management', 'admin(trustee)', 'ADMIN', 'admin']).exists()
            or user.groups.filter(name__in=CLERK_GROUPS).exists()
        ):
            return True
        staff = getattr(user, 'staff', None)
        if staff and str(getattr(staff, 'category', '') or '').strip().upper() in (['INVENTORY', 'PRINCIPAL', 'TRUSTEE', 'FEES MANAGEMENT', 'FEE MANAGEMENT', 'ACCOUNTANT'] + CLERK_ROLES):
            return True
        from .models import School
        if School.objects.filter(login_id=user.id).exists():
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
        if role in CLERK_ROLES or role in ["PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=["PRINCIPAL", "admin(trustee)", "ADMIN", "admin", "principal"] + CLERK_GROUPS).exists()
        )
        
IsClerkOrPrincipalOrAdmin = IsClerkOrPrincipal


class IsClerkOrAdmin(BasePermission):
    """
    Grants access to Clerk, Assistant Clerk, Principal, Trustee, and Admin users for HR & configurations.
    Excludes Fee Management, Librarian, Inventory, and general staff roles.
    """
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
        if staff and (str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL", "TRUSTEE", "ADMIN"] or str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES):
            return True
        return (
            user.groups.filter(name__in=CLERK_GROUPS).exists()
            or user.groups.filter(name__in=[
                "PRINCIPAL", "principal", "Principal",
                "VICE PRINCIPAL", "vice principal", "Vice Principal",
                "admin(trustee)", "trustee", "Trustee",
                "ADMIN", "admin", "Admin",
                "super_admin", "superadmin", "Super Admin",
            ] + CLERK_GROUPS).exists()
        )


class IsHRAttendanceAdmin(BasePermission):
    """
    Grants access to Principal, Vice Principal, HR, Trustee, and Admin users specifically for
    Attendance Administration (settings, corrections, regularization approvals).
    Explicitly denies Fees Management, Librarian, Inventory, Teacher, and general staff roles.
    Clerk and Assistant Clerk do NOT automatically get approval/correction permission
    unless explicitly assigned to an HR/Attendance Admin group.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()

        # Explicit blacklist: these roles should NEVER administer school-wide HR/Attendance
        if role in ["FEES MANAGEMENT", "FEE MANAGEMENT", "LIBRARIAN", "INVENTORY", "STUDENT", "PARENT", "TEACHER"]:
            return False

        # Clerk and Assistant Clerk: do NOT automatically get approval/correction permission
        if role in ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK", "FEES_CLERK"]:
            return user.groups.filter(name__in=["HR_ADMIN", "ATTENDANCE_ADMIN", "Attendance Admin", "HR Admin", "HR", "hr"]).exists()

        if role in ["HR", "HR_ADMIN", "ATTENDANCE_ADMIN", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN"]:
            return True

        staff = getattr(user, "staff", None)
        if staff:
            cat = str(getattr(staff, "category", "") or "").strip().upper()
            if cat in ["FEES MANAGEMENT", "FEE MANAGEMENT", "LIBRARIAN", "INVENTORY", "TEACHER"]:
                return False
            if cat in ["CLERK", "ASSISTANT CLERK", "ASSISTANT_CLERK"]:
                return user.groups.filter(name__in=["HR_ADMIN", "ATTENDANCE_ADMIN", "Attendance Admin", "HR Admin", "HR", "hr"]).exists()
            if cat in ["HR", "HR_ADMIN", "PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN"]:
                return True

        return (
            user.groups.filter(name__in=[
                "PRINCIPAL", "principal", "Principal",
                "VICE PRINCIPAL", "vice principal", "Vice Principal",
                "admin(trustee)", "trustee", "Trustee",
                "ADMIN", "admin", "Admin",
                "super_admin", "superadmin", "Super Admin",
                "HR", "hr", "HR_ADMIN", "ATTENDANCE_ADMIN", "Attendance Admin",
            ]).exclude(name__in=["FEES MANAGEMENT", "Fee Management", "fees management"]).exists()
        )


class IsPrincipalOrTrustee(BasePermission):
    """Principal, Trustee, and System Admin can approve/reject leave requests. Non-approver roles (Teachers, Librarians, Clerks) cannot."""
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in ["PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE", "ADMIN", "SUPERADMIN", "SUPER_ADMIN", "ADMIN(TRUSTEE)"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in ["PRINCIPAL", "VICE PRINCIPAL", "TRUSTEE"]:
            return True
        return (
            user.groups.filter(name__iexact="PRINCIPAL").exists()
            or user.groups.filter(name__iexact="VICE PRINCIPAL").exists()
            or user.groups.filter(name__iexact="TRUSTEE").exists()
            or user.groups.filter(name__iexact="ADMIN(TRUSTEE)").exists()
            or user.groups.filter(name__in=["PRINCIPAL", "principal", "Principal", "admin(trustee)", "ADMIN", "admin", "TRUSTEE", "trustee"]).exists()
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
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
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
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, 'role', '') or "").strip().upper()
        if role in ['LIBRARIAN', 'PRINCIPAL', 'ADMIN', 'SUPERADMIN', 'SUPER_ADMIN']:
            return True
        group_names = [g.name.strip().upper() for g in user.groups.all()]
        if any(g in ['LIBRARIAN', 'PRINCIPAL', 'SUPERADMIN', 'SUPER_ADMIN'] for g in group_names):
            return True
        staff = getattr(user, 'staff', None) or Staff.objects.filter(user=user).first()
        if staff:
            cat = str(getattr(staff, 'category', '') or "").strip().upper()
            if cat in ['LIBRARIAN', 'PRINCIPAL', 'ADMIN']:
                return True
            if role == 'LIBRARIAN':
                return True
        return False


class IsClerkOrReadOnly(BasePermission):
    """
    Allows read (GET, HEAD, OPTIONS) to any authenticated user.
    Restricts write/create/update/delete strictly to Clerk roles and Administrators.
    Principal, Trustee, Teacher, etc. cannot create or modify.
    """
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True
        role = str(getattr(user, "role", "") or "").strip().upper()
        if role in CLERK_ROLES or role in ["ADMIN", "SUPERADMIN", "SUPER_ADMIN"]:
            return True
        staff = getattr(user, "staff", None)
        if staff and str(getattr(staff, "category", "") or "").strip().upper() in CLERK_ROLES:
            return True
        return user.groups.filter(name__in=CLERK_GROUPS + ["ADMIN", "admin"]).exists()


class IsFeeTypePermission(BasePermission):
    """
    Permission class for FeeTypeViewSet:
    - Allows read-only access (SAFE_METHODS: GET, HEAD, OPTIONS) for:
      - Authenticated users in Inventory roles/groups (Isinventory, 'Inventory Manager', 'INVENTORY', 'inventory')
      - Authenticated users in Clerk roles/groups
      - Authenticated users in Fee Management roles/groups
      - Authenticated users with the 'sms_app.view_feetype' permission
      - Principals, Admins, SuperAdmins, and Staff
    - Mutating methods (POST, PUT, PATCH, DELETE) remain strictly restricted to:
      - Fee Managers, Clerks, Principals, Admins, and SuperAdmins.
    """
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False

        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
            return True

        is_fee_or_clerk = (
            IsFeeManager().has_permission(request, view)
            or IsClerkOrPrincipal().has_permission(request, view)
        )

        if request.method in SAFE_METHODS:
            if is_fee_or_clerk:
                return True
            if Isinventory().has_permission(request, view):
                return True
            if user.has_perm("sms_app.view_feetype"):
                return True
            role = str(getattr(user, "role", "") or "").strip().upper()
            if role in ["INVENTORY", "INVENTORY MANAGER", "INVENTORY_MANAGER"] or role in CLERK_ROLES:
                return True
            if user.groups.filter(name__in=["Inventory Manager", "INVENTORY", "inventory", "inventory manager", "Clerk", "CLERK", "clerk"] + CLERK_GROUPS).exists():
                return True
            staff = getattr(user, "staff", None)
            if staff and str(getattr(staff, "category", "") or "").strip().upper() in (["INVENTORY", "INVENTORY MANAGER"] + CLERK_ROLES):
                return True
            return False

        return is_fee_or_clerk


