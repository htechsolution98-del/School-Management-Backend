from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import School, Staff, SchoolFeature


class CanManageStaffStatus(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.is_active:
            return False
        roles = {str(getattr(user, 'role', '') or '').strip().lower()}
        roles.update(str(name).strip().lower() for name in user.groups.values_list('name', flat=True))
        staff = Staff.objects.filter(user=user).first()
        if staff:
            roles.add(str(staff.category or '').strip().lower())
        return bool(roles & {'trustee', 'admin(trustee)', 'principal'})


class StaffStatusSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)

    class Meta:
        model = Staff
        fields = ['id', 'name', 'email', 'mobile', 'category', 'department_name', 'is_active', 'created_at']
        read_only_fields = fields


class StatusInputSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=True)


from .trustee_staff_access import TrusteeStaffReadOnlyMixin

class StaffActivationViewSet(TrusteeStaffReadOnlyMixin, ReadOnlyModelViewSet):
    trustee_report_only = True
    permission_classes = [IsAuthenticated, CanManageStaffStatus]
    serializer_class = StaffStatusSerializer
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        school = getattr(user, 'school', None)
        if not school:
            member = Staff.objects.filter(user=user).first()
            school = member.school if member else None
        if not school:
            school = School.objects.filter(login_id=user).first()
        if not school:
            return Staff.objects.none()
        return Staff.objects.filter(school=school).select_related('department', 'user').order_by('-created_at', '-id')

    @action(detail=True, methods=['patch'], url_path='status')
    def set_status(self, request, pk=None):
        payload = StatusInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        desired = payload.validated_data['is_active']
        with transaction.atomic():
            member = self.get_queryset().select_related(None).select_for_update().filter(pk=pk).first()
            if member is None:
                from rest_framework.exceptions import NotFound
                raise NotFound('Staff member not found.')
            if member.user_id == request.user.pk and not desired:
                raise serializers.ValidationError({'detail': 'You cannot deactivate your own account.'})
            if desired:
                assignment = SchoolFeature.objects.select_related('feature').filter(school_id=member.school_id, feature__name__iexact=member.category).first()
                if assignment and (not assignment.is_enabled or not assignment.feature.is_active):
                    raise serializers.ValidationError({'detail': 'This staff role is disabled for your school. Enable the feature before activating staff.'})
            member.is_active = desired
            member.save(update_fields=['is_active', 'updated_at'])
            if member.user_id:
                get_user_model().objects.filter(pk=member.user_id).update(is_active=desired)
        return Response(self.get_serializer(member).data)
