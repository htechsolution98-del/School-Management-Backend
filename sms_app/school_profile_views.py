import os
import logging
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import School, Staff
from .school_profile_models import SchoolProfile
from .school_profile_serializers import SchoolProfileSerializer, SchoolProfileAssetUploadSerializer

logger = logging.getLogger(__name__)


class IsTrusteeOrSuperAdmin(BasePermission):
    """
    Strict RBAC permission: Only users with 'TRUSTEE' or 'SUPERADMIN' roles
    can access or modify institutional profiles and branding assets.
    """
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not user.is_active:
            return False

        if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
            return True

        roles = {str(getattr(user, "role", "") or "").strip().lower()}
        roles.update(str(r).strip().lower() for r in user.groups.values_list("name", flat=True))
        roles.update(str(r or "").strip().lower() for r in Staff.objects.filter(user=user).values_list("category", flat=True))

        allowed = {
            "trustee",
            "admin(trustee)",
            "superadmin",
            "super_admin",
            "super admin",
            "admin",
        }
        return bool(roles & allowed)


def is_superadmin_user(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    roles = {str(getattr(user, "role", "") or "").strip().lower()}
    roles.update(str(r).strip().lower() for r in user.groups.values_list("name", flat=True))
    return bool(roles & {"superadmin", "super_admin", "super admin"})


def get_school_for_user(request):
    """
    Resolves the active School entity with strict Row-Level Security (RLS) tenant isolation.
    - Superadmins can view/edit any school by providing school_id (query param or body).
    - Trustees / Staff are strictly isolated to their own school. If they try to request
      another tenant's school_id, a 403 Forbidden PermissionDenied exception is raised.
    """
    from rest_framework.exceptions import PermissionDenied, NotFound

    user = request.user
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    is_super = is_superadmin_user(user)

    # 1. Resolve user's actual assigned home school
    home_school = getattr(user, "school", None)
    if not home_school:
        member = Staff.objects.filter(user=user).select_related("school").first()
        home_school = member.school if member else None
    if not home_school:
        home_school = School.objects.filter(login_id=user).first()

    # 2. Extract requested school_id from query params or payload
    requested_school_id = request.query_params.get("school_id")
    if not requested_school_id and isinstance(request.data, dict):
        requested_school_id = request.data.get("school_id")

    # 3. Superadmin bypass: can access requested school or first available
    if is_super:
        if requested_school_id:
            target = School.objects.filter(id=requested_school_id).first()
            if target:
                return target
            raise NotFound(f"School tenant with ID {requested_school_id} not found.")
        if home_school:
            return home_school
        return School.objects.first()

    # 4. Strict Tenant Isolation for Trustee / Non-SuperAdmin
    if not home_school:
        raise PermissionDenied("No authorized school tenant associated with your account.")

    if requested_school_id and str(requested_school_id) != str(home_school.id):
        logger.warning(
            "Security Alert: User %s (school_id=%s) attempted to access tenant school_id=%s",
            user.id,
            home_school.id,
            requested_school_id,
        )
        raise PermissionDenied("Forbidden: You are not authorized to view or modify another school tenant's profile.")

    return home_school


class SchoolProfileView(APIView):
    """
    GET: Retrieve institutional details, billing credentials, and media asset URLs.
    PUT / PATCH: Update institutional profile attributes.
    Protected with strict RBAC (Trustee or Super Admin only).
    """
    permission_classes = [IsAuthenticated, IsTrusteeOrSuperAdmin]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get(self, request):
        school = get_school_for_user(request)
        if not school:
            return Response(
                {"detail": "No school tenant found associated with your account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile = SchoolProfile.get_or_create_for_school(school)
        serializer = SchoolProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        return self.patch(request)

    def patch(self, request):
        school = get_school_for_user(request)
        if not school:
            return Response(
                {"detail": "No school tenant found associated with your account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        profile = SchoolProfile.get_or_create_for_school(school)
        serializer = SchoolProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            updated_profile = serializer.save()
            return Response(
                {
                    "message": "Institutional school profile updated successfully.",
                    "data": SchoolProfileSerializer(updated_profile).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SchoolProfileAssetUploadView(APIView):
    """
    Direct Cloudinary image upload endpoint for branding assets
    (logos, signatures, seals, watermarks, backgrounds).
    Serves as an authorized server-side fallback or direct uploader.
    """
    permission_classes = [IsAuthenticated, IsTrusteeOrSuperAdmin]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = SchoolProfileAssetUploadSerializer(data=request.data)
        if not serializer.is_valid():
            file_error = serializer.errors.get("file")
            first_msg = (
                file_error[0]
                if isinstance(file_error, list) and file_error
                else str(file_error)
                if file_error
                else "Invalid upload payload."
            )
            return Response(
                {
                    "detail": first_msg,
                    "file": file_error or first_msg,
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = serializer.validated_data["file"]
        asset_type = serializer.validated_data.get("asset_type", "branding")
        school = get_school_for_user(request)
        folder = f"school_{school.id if school else 'common'}/branding"

        # Try server-side Cloudinary upload
        try:
            import cloudinary
            import cloudinary.uploader

            upload_result = cloudinary.uploader.upload(
                file_obj,
                folder=folder,
                resource_type="auto",
                overwrite=True,
                tags=["school_profile", asset_type, f"school_{school.id if school else 0}"]
            )
            secure_url = upload_result.get("secure_url") or upload_result.get("url")
            public_id = upload_result.get("public_id")

            return Response(
                {
                    "url": secure_url,
                    "public_id": public_id,
                    "asset_type": asset_type,
                    "format": upload_result.get("format"),
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            logger.exception("Cloudinary upload failed: %s", str(e))
            # Fallback to local / default storage if Cloudinary fails or offline
            try:
                from django.core.files.storage import default_storage
                saved_path = default_storage.save(f"{folder}/{file_obj.name}", file_obj)
                file_url = request.build_absolute_uri(default_storage.url(saved_path))
                return Response(
                    {
                        "url": file_url,
                        "asset_type": asset_type,
                        "note": "Uploaded via server storage fallback",
                    },
                    status=status.HTTP_201_CREATED,
                )
            except Exception as fallback_err:
                return Response(
                    {"detail": f"Failed to upload asset: {str(e)}"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

