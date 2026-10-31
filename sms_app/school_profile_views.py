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
from .school_profile_serializers import SchoolProfileSerializer

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


def get_school_for_user(request):
    """
    Helper to resolve the active School entity for the current user.
    Supports Staff linkage, direct ownership, or superuser school selection.
    """
    user = request.user
    school = getattr(user, "school", None)

    if not school:
        member = Staff.objects.filter(user=user).select_related("school").first()
        school = member.school if member else None

    if not school:
        school = School.objects.filter(login_id=user).first()

    if not school and (user.is_superuser or user.is_staff):
        school_id = request.query_params.get("school_id") or (
            request.data.get("school_id") if isinstance(request.data, dict) else None
        )
        if school_id:
            try:
                school = School.objects.filter(id=school_id).first()
            except Exception:
                pass
        if not school:
            school = School.objects.first()

    return school


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
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response(
                {"detail": "No file uploaded. Please attach a file under 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Enforce max 10MB limit
        if file_obj.size > 10 * 1024 * 1024:
            return Response(
                {"detail": "File size exceeds 10MB limit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        school = get_school_for_user(request)
        asset_type = request.data.get("asset_type", "branding")
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

