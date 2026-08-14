from rest_framework.permissions import BasePermission

class Is_super_admin(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.groups.filter(name='super_admin').exists())
        )

class Is_admin_trustee(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="admin(trustee)").exists()
        )




class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="CLERK").exists()
        )




class IsFeeManager(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="FEES MANAGEMENT").exists()
        )




class Isprincipal(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="PRINCIPAL").exists()
        )




class Isstudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="STUDENT").exists()
        )


class Isparent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="PARENT").exists()
        )



class Isteacher(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="TEACHER").exists()
        )



class Isinventory(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="INVENTORY").exists()
        )




class IsTempUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="temp_user").exists()
        )





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

        return UserModuleAccess.objects.filter(
            user=user, module__code=module_code, module__is_active=True
        ).exists()

class IsAdminTrusteeOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name__in=["admin(trustee)", "PRINCIPAL"]).exists()
        )

class IsClerkOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="admin(trustee)").exists()
        )




class IsCLerk(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="CLERK").exists()
        )




class IsFeeManager(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="FEES MANAGEMENT").exists()
        )




class Isprincipal(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="PRINCIPAL").exists()
        )




class Isstudent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="STUDENT").exists()
        )


class Isparent(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="PARENT").exists()
        )



class Isteacher(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="TEACHER").exists()
        )



class Isinventory(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="INVENTORY").exists()
        )




class IsTempUser(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name="temp_user").exists()
        )





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

        return UserModuleAccess.objects.filter(
            user=user, module__code=module_code, module__is_active=True
        ).exists()

class IsAdminTrusteeOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.groups.filter(name__in=["admin(trustee)", "PRINCIPAL"]).exists()
        )

class IsClerkOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        role = getattr(user, "role", "")
        if role in ["CLERK", "PRINCIPAL", "TRUSTEE", "ADMIN", "FEES MANAGEMENT"]:
            return True
        return user.groups.filter(name__in=["CLERK", "PRINCIPAL", "admin(trustee)", "FEES MANAGEMENT"]).exists()


class IsPrincipalOrTrustee(BasePermission):
    """Principal, Clerk, Trustee and Admin can approve/reject leave requests."""
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        role = getattr(user, "role", "")
        if role in ["CLERK", "PRINCIPAL", "TRUSTEE", "ADMIN"]:
            return True
        return user.groups.filter(name__in=["CLERK", "PRINCIPAL", "admin(trustee)"]).exists()

class IsClerkOrTrustee(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        return user.groups.filter(name__in=['CLERK', 'admin(trustee)']).exists()


class IsClerkOrTempUser(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'is_superuser', False):
            return True
        role = getattr(user, 'role', '')
        if role in ['CLERK', 'PRINCIPAL', 'ADMIN', 'TEMP_USER']:
            return True
        return user.groups.filter(name__in=['CLERK', 'PRINCIPAL', 'TEMP_USER']).exists()



