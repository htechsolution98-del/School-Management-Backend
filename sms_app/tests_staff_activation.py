from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from .authentication import CookieJWTAuthentication
from .models import School, Staff, Feature, SchoolFeature


class StaffActivationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.trustee = User.objects.create_user(username='activation-trustee', role='admin(trustee)')
        owner = User.objects.create_user(username='activation-other-owner', role='admin(trustee)')
        self.school = School.objects.create(name='Activation school', code='activation-school', login_id=self.trustee)
        self.other_school = School.objects.create(name='Other school', code='activation-other', login_id=owner)
        self.trustee.school = self.school
        self.trustee.save()
        self.principal = User.objects.create_user(username='activation-principal', role='principal', school=self.school)
        self.teacher = User.objects.create_user(username='activation-teacher', role='teacher', school=self.school)
        self.member = Staff.objects.create(name='Test teacher', school=self.school, user=self.teacher, category='teacher')
        self.other = Staff.objects.create(name='Other teacher', school=self.other_school, category='teacher')
        self.client = APIClient()

    def status_url(self, member=None):
        return reverse('staff-activation-set-status', args=[(member or self.member).pk])

    def test_principal_lists_only_their_school(self):
        for user in [self.principal]:
            self.client.force_authenticate(user)
            response = self.client.get(reverse('staff-activation-list'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row['id'] for row in response.data], [self.member.pk])
            self.assertIn('created_at', response.data[0])

    def test_principal_and_trustee_deactivate_and_reactivate_login(self):
        for user in [self.principal, self.trustee]:
            self.client.force_authenticate(user)
            for desired in [False, True]:
                response = self.client.patch(self.status_url(), {'is_active': desired}, format='json')
                self.assertEqual(response.status_code, 200, response.data)
                self.member.refresh_from_db()
                self.teacher.refresh_from_db()
                self.assertEqual(self.member.is_active, desired)
                self.assertEqual(self.teacher.is_active, desired)

    def test_cross_school_write_is_rejected(self):
        self.client.force_authenticate(self.principal)
        response = self.client.patch(self.status_url(self.other), {'is_active': False}, format='json')
        self.assertEqual(response.status_code, 404)
        self.other.refresh_from_db()
        self.assertTrue(self.other.is_active)

    def test_teacher_cannot_list_or_change_status(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self.client.get(reverse('staff-activation-list')).status_code, 403)
        self.assertEqual(self.client.patch(self.status_url(), {'is_active': False}, format='json').status_code, 403)

    def test_anonymous_is_rejected(self):
        self.assertIn(self.client.get(reverse('staff-activation-list')).status_code, [401, 403])

    def test_missing_and_invalid_status_leave_data_unchanged(self):
        self.client.force_authenticate(self.principal)
        for payload in [{}, {'is_active': 'wrong'}, {'is_active': None}]:
            self.assertEqual(self.client.patch(self.status_url(), payload, format='json').status_code, 400)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_self_deactivation_is_rejected(self):
        member = Staff.objects.create(name='Principal', school=self.school, user=self.principal, category='principal')
        self.client.force_authenticate(self.principal)
        self.assertEqual(self.client.patch(self.status_url(member), {'is_active': False}, format='json').status_code, 400)
        self.principal.refresh_from_db()
        self.assertTrue(self.principal.is_active)

    def test_disabled_feature_prevents_activation(self):
        feature, _ = Feature.objects.get_or_create(name='teacher')
        SchoolFeature.objects.update_or_create(school=self.school, feature=feature, defaults={'is_enabled': False})
        self.member.is_active = False
        self.member.save()
        self.client.force_authenticate(self.principal)
        self.assertEqual(self.client.patch(self.status_url(), {'is_active': True}, format='json').status_code, 400)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)

    def test_owner_without_school_foreign_key_uses_owned_school(self):
        self.school.login_id = self.trustee
        self.school.save()
        self.trustee.school = None
        self.trustee.save()
        self.client.force_authenticate(self.trustee)
        response = self.client.get(reverse('trustee-staff-report'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.data['staff']['results']], [self.member.pk])

    def test_group_role_is_supported(self):
        self.trustee.role = ''
        self.trustee.save()
        group, _ = Group.objects.get_or_create(name='trustee')
        self.trustee.groups.add(group)
        self.client.force_authenticate(self.trustee)
        self.assertEqual(self.client.get(reverse('trustee-staff-report')).status_code, 200)
        self.assertEqual(self.client.get(reverse('staff-activation-list')).status_code, 200)

    def test_role_without_school_cannot_see_or_change_staff(self):
        user = get_user_model().objects.create_user(username='unassigned-principal', role='principal')
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(reverse('staff-activation-list')).data, [])
        self.assertEqual(self.client.patch(self.status_url(), {'is_active': False}, format='json').status_code, 404)

    def test_globally_inactive_feature_prevents_activation(self):
        feature, _ = Feature.objects.get_or_create(name='teacher')
        feature.is_active = False
        feature.save()
        self.client.force_authenticate(self.principal)
        self.assertEqual(self.client.patch(self.status_url(), {'is_active': True}, format='json').status_code, 400)

    def test_database_failure_rolls_back_staff_status(self):
        self.client.force_authenticate(self.principal)
        with patch('django.db.models.query.QuerySet.update', side_effect=RuntimeError('Simulated login update failure')):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.status_url(), {'is_active': False}, format='json')
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_deactivated_login_cannot_use_existing_jwt(self):
        token = RefreshToken.for_user(self.teacher).access_token
        self.client.force_authenticate(self.principal)
        self.client.patch(self.status_url(), {'is_active': False}, format='json')
        with self.assertRaises(AuthenticationFailed):
            CookieJWTAuthentication().get_user(token)
