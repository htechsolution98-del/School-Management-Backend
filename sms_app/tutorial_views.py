import re
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
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
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
            # Role alias handling
            if role_upper in ['FEES_MANAGEMENT', 'ACCOUNTANT', 'FINANCE']:
                role_upper = 'FEES'
            elif role_upper in ['LIBRARIAN', 'LIBRARY', 'LIB']:
                role_upper = 'LIBRARIAN'
            elif role_upper in ['SUPER_ADMIN', 'SUPER-ADMIN']:
                role_upper = 'SUPERADMIN'
            qs = qs.filter(Q(role=role_upper) | Q(role='GLOBAL'))
        return qs

    def create(self, request, *args, **kwargs):
        role = request.data.get('role', '').upper().strip()
        route_path = request.data.get('route_path', '').strip().rstrip('/')
        if route_path and not route_path.startswith('/'):
            route_path = '/' + route_path

        if role in ['FEES_MANAGEMENT', 'ACCOUNTANT', 'FINANCE']:
            role = 'FEES'
        elif role in ['LIBRARIAN', 'LIBRARY', 'LIB']:
            role = 'LIBRARIAN'
        elif role in ['SUPER_ADMIN', 'SUPER-ADMIN']:
            role = 'SUPERADMIN'

        existing = PageTutorial.objects.filter(role=role, route_path=route_path).first()
        if existing:
            serializer = self.get_serializer(existing, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data, status=status.HTTP_200_OK)

        return super().create(request, *args, **kwargs)

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
        elif role in ['LIBRARIAN', 'LIBRARY', 'LIB']:
            role = 'LIBRARIAN'
        elif role in ['SUPER_ADMIN', 'SUPER-ADMIN']:
            role = 'SUPERADMIN'

        candidate_paths = [path]
        # Strip trailing numeric or UUID identifiers (e.g. /clerk/student-profiles/29 -> /clerk/student-profiles)
        stripped = re.sub(r'/\d+$', '', path)
        if stripped != path and stripped:
            candidate_paths.append(stripped)
        uuid_stripped = re.sub(r'/[0-9a-f-]{36}$', '', path, flags=re.I)
        if uuid_stripped not in candidate_paths and uuid_stripped:
            candidate_paths.append(uuid_stripped)
        if '/' in path:
            parent = path.rsplit('/', 1)[0]
            if parent and parent not in candidate_paths:
                candidate_paths.append(parent)

        for candidate in candidate_paths:
            query = Q(route_path=candidate) | Q(route_path=candidate + '/')
            tutorial = None
            if role:
                tutorial = PageTutorial.objects.filter(query, role=role).first()
                if not tutorial:
                    tutorial = PageTutorial.objects.filter(query, role='GLOBAL').first()
            else:
                tutorial = PageTutorial.objects.filter(query).first()

            if tutorial:
                serializer = self.get_serializer(tutorial)
                return Response(serializer.data)

        return Response(
            {"detail": "Default tutorial active.", "custom": False, "route_path": path, "role": role},
            status=status.HTTP_200_OK
        )

