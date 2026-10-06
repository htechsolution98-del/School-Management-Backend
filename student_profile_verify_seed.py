"""Temporary browser-test database setup, separate from the application's database."""
import io
import json
import os
from pathlib import Path
os.environ["DJANGO_SETTINGS_MODULE"] = "sms.student_profile_test_settings"
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from rest_framework_simplejwt.tokens import RefreshToken
from sms_app.models import CustomUser, School, SchoolClass, Student, AdmissionForm, Admission, FormSection, FormField, DocumentField, AdmissionFieldValue, StudentExtraData
call_command("migrate", interactive=False, run_syncdb=True, stdout=io.StringIO(), verbosity=0)
owner = CustomUser.objects.create_user(username="browser-profile-owner", role="super_admin")
school = School.objects.create(login_id=owner, name="Browser Verification School")
clerk = CustomUser.objects.create_user(username="browser-profile-clerk", role="CLERK", school=school)
cls = SchoolClass.objects.create(school=school, school_class="Std 1")
other_class = SchoolClass.objects.create(school=school, school_class="Std 2")
form = AdmissionForm.objects.bulk_create([AdmissionForm(school=school, title="Browser Profile Form")])[0]
admission = Admission.objects.create(school=school, form=form, admission_number="BROWSER-001")
student = Student.objects.create(school=school, school_class=cls, admission=admission, name="Aarav", surname="Patel", father_name="Rajesh Patel", mother_name="Rina Patel", gr_no="BROWSER-GR001", mobile="9876543210", division="A", roll_no="1")
Student.objects.create(school=school, school_class=other_class, name="Diya", surname="Shah", gr_no="BROWSER-GR002", division="B", roll_no="2")
StudentExtraData.objects.create(student=student, place_of_birth="Ahmedabad", religion="Recorded religion")
section = FormSection.objects.create(school=school, form=form, title="Contact & Address", order=1)
field = FormField.objects.create(section=section, label="Home address", field_type="text", order=1)
AdmissionFieldValue.objects.create(admission=admission, field=field, value="Ahmedabad, Gujarat")
slot = DocumentField.objects.create(school=school, form=form, label="Birth Certificate", is_required=True)
path = Path(settings.DATABASES["default"]["NAME"]).parent / "browser-fixture.json"
path.write_text(json.dumps({"token": str(RefreshToken.for_user(clerk).access_token), "student_id": student.id, "slot_id": slot.id}), encoding="utf-8")
print("Isolated browser verification data ready.")
