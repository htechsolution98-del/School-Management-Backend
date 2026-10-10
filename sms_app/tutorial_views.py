from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .tutorial_models import PageTutorial
from .tutorial_serializers import PageTutorialSerializer


class IsSuperAdminOrReadOnly(permissions.BasePermission):
    """
    Super Admin has full CRUD access.
    Authenticated users of supported roles have read-only access.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user.is_superuser
            or request.user.groups.filter(name="super_admin").exists()
        )


class PageTutorialViewSet(viewsets.ModelViewSet):
    queryset = PageTutorial.objects.all()
    serializer_class = PageTutorialSerializer
    permission_classes = [IsSuperAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        role = self.request.query_params.get('role')
        if role:
            role_upper = role.upper().strip()
            # Fees alias handling
            if role_upper in ['FEES_MANAGEMENT', 'ACCOUNTANT', 'FINANCE']:
                role_upper = 'FEES'
            qs = qs.filter(Q(role=role_upper) | Q(role='GLOBAL'))
        return qs

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=['get'], url_path='by-path')
    def get_by_path(self, request):
        path = request.query_params.get('path', '').strip().rstrip('/')
        role = request.query_params.get('role', '').upper().strip()

        if not path:
            return Response(
                {"detail": "Path parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if role in ['FEES_MANAGEMENT', 'ACCOUNTANT', 'FINANCE']:
            role = 'FEES'

        # First search for exact (role, path)
        query = Q(route_path=path) | Q(route_path=path + '/')
        if role:
            tutorial = PageTutorial.objects.filter(query, role=role).first()
            if not tutorial:
                # Try GLOBAL
                tutorial = PageTutorial.objects.filter(query, role='GLOBAL').first()
        else:
            tutorial = PageTutorial.objects.filter(query).first()

        if tutorial:
            serializer = self.get_serializer(tutorial)
            return Response(serializer.data)

        return Response(
            {"detail": "No custom tutorial found for this path.", "route_path": path, "role": role},
            status=status.HTTP_404_NOT_FOUND
        )
