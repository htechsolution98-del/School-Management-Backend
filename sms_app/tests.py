from django.test import TestCase
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from django.contrib.auth import get_user_model

from sms_app.models import School, Admission, Student
from sms_app.serializer import ClerkVerifySerializer

User = get_user_model()


class ClerkVerifySerializerTest(TestCase):
    def setUp(self):
        self.admin1 = User.objects.create_user(username="admin1", password="pass")
        self.admin2 = User.objects.create_user(username="admin2", password="pass")

        self.school1 = School.objects.create(login_id=self.admin1, name="School 1")
        self.school2 = School.objects.create(login_id=self.admin2, name="School 2")

        self.clerk1 = User.objects.create_user(
            username="clerk1", password="pass", school=self.school1
        )
        self.clerk2 = User.objects.create_user(
            username="clerk2", password="pass", school=self.school2
        )

        self.admission1 = Admission.objects.create(
            school=self.school1, admission_number="ADM-001", status="pending"
        )
        self.admission2 = Admission.objects.create(
            school=self.school2, admission_number="ADM-002", status="pending"
        )

        self.request_factory = APIRequestFactory()

    def test_validate_rejects_duplicate_gr_no_within_same_school(self):
        Student.objects.create(school=self.school1, gr_no="1001")

        request = self.request_factory.patch("/api/clerk_verify/ADM-001/")
        request.user = self.clerk1

        serializer = ClerkVerifySerializer(context={"request": request})

        with self.assertRaises(serializers.ValidationError) as cm:
            serializer.validate({"gr_no": "1001"})

        self.assertEqual(
            cm.exception.detail,
            {"message": "A student with this gr_no already exists for this school."},
        )

    def test_validate_allows_duplicate_gr_no_across_different_schools(self):
        Student.objects.create(school=self.school1, gr_no="1001")

        request = self.request_factory.patch("/api/clerk_verify/ADM-002/")
        request.user = self.clerk2

        serializer = ClerkVerifySerializer(context={"request": request})

        # Should not raise for a duplicate gr_no in a different school
        try:
            validated_data = serializer.validate({"gr_no": "1001"})
        except serializers.ValidationError:
            self.fail("ClerkVerifySerializer.validate() raised ValidationError unexpectedly")

        self.assertEqual(validated_data, {"gr_no": "1001"})
