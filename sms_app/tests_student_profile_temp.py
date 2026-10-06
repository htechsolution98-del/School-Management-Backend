import tempfile
from unittest.mock import patch
from django.db import connection, DatabaseError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from .models import CustomUser, School, SchoolClass, Student, Admission, AdmissionForm, FormSection, FormField, DocumentField, AdmissionDocument, AdmissionFieldValue, StudentDocument, RTEDocument
from .serializer import ManualStudentSerializer, AdmissionFieldValueSerializer


class StudentProfileTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.settings = override_settings(MEDIA_ROOT=self.folder.name)
        self.settings.enable()
        self.addCleanup(self.folder.cleanup)
        self.addCleanup(self.settings.disable)
        self.owner = CustomUser.objects.create_user(username="profile-owner", role="super_admin")
        self.school = School.objects.create(login_id=self.owner, name="Profile School")
        self.other_school = School.objects.create(login_id=self.owner, name="Other Profile School")
        self.clerk = CustomUser.objects.create_user(username="profile-clerk", role="CLERK", school=self.school)
        self.client = APIClient()
        self.client.force_authenticate(self.clerk)
        self.cls = SchoolClass.objects.create(school=self.school, school_class="Std 1")
        self.form = AdmissionForm.objects.bulk_create([AdmissionForm(school=self.school, title="Profile admission")])[0]
        self.admission = Admission.objects.create(school=self.school, form=self.form, admission_number="PROFILE-001")
        self.student = Student.objects.create(school=self.school, school_class=self.cls, admission=self.admission, name="Aarav", surname="Patel", gr_no="GR001", division="A", roll_no="1")
        self.other = Student.objects.create(school=self.other_school, name="External", gr_no="GR001")
        self.slot = DocumentField.objects.create(school=self.school, form=self.form, label="Birth Certificate", is_required=True)
        section = FormSection.objects.create(school=self.school, form=self.form, title="Identity", order=1)
        self.aadhaar_field = FormField.objects.create(section=section, label="Aadhaar Number", field_type="text", order=1, map_to_student_field="aadhar_number")
        AdmissionFieldValue.objects.create(admission=self.admission, field=self.aadhaar_field, value="")
        self.url = f"/api/students/{self.student.id}/"

    def pdf(self, name="document.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4\nstudent document", "application/pdf")

    def upload(self, **data):
        return self.client.post(self.url + "documents/", {"file": self.pdf(), "title": "Record", **data}, format="multipart")

    def test_document_content_and_access_control(self):
        document = self.upload().data["documents"][0]
        endpoint = self.url + f"documents/{document['id']}/content/"
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4\nstudent document")
        response.close()
        response = self.client.get(endpoint + "?download=1")
        self.assertIn("attachment", response["Content-Disposition"])
        response.close()
        self.assertEqual(self.client.get(f"/api/students/{self.other.id}/documents/{document['id']}/content/").status_code, 404)
        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get(endpoint).status_code, (401, 403))

    def test_each_document_verifies_independently_and_replacement_resets(self):
        sources = [{"source": "adm", "document_field": self.slot.id}, {"source": "std"}, {"source": "rte"}]
        for source in sources:
            response = self.client.post(self.url + "documents/", {"file": self.pdf(), **source, **({"title": "Record"} if source["source"] != "adm" else {})}, format="multipart")
            self.assertEqual(response.status_code, 201, response.data)
        profile = self.client.get(self.url).data
        documents = profile["documents"]
        for item in documents:
            endpoint = self.url + f"documents/{item['id']}/"
            response = self.client.patch(endpoint, {"is_verified": True, "expected_file": item["file_name"]}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            verified = next(d for d in response.data["documents"] if d["id"] == item["id"])
            self.assertTrue(verified["is_verified"])
            self.assertEqual(verified["verification_scope"], "document")
            self.assertIsNotNone(verified["verified_at"])
            self.assertEqual(verified["verified_by_name"], self.clerk.username)
            self.assertFalse(response.data["is_verified"])
            self.assertTrue(all(not d["is_verified"] for d in response.data["documents"] if d["id"] != item["id"]))
            response = self.client.patch(endpoint, {"file": self.pdf("replacement.pdf"), "expected_file": item["file_name"]}, format="multipart")
            self.assertEqual(response.status_code, 200, response.data)
            replaced = next(d for d in response.data["documents"] if d["id"] == item["id"])
            self.assertFalse(replaced["is_verified"])
            self.assertIsNone(replaced["verified_at"])
            self.assertIsNone(replaced["verified_by_name"])
        self.client.patch(self.url, {"is_verified": True}, format="json")
        self.assertTrue(all(not d["is_verified"] for d in self.client.get(self.url).data["documents"]))
        self.assertEqual(self.client.patch(f"/api/students/{self.other.id}/documents/{documents[0]['id']}/", {"is_verified": True}, format="json").status_code, 404)

    def test_shared_fields_and_student_values_are_school_scoped(self):
        peer = Student.objects.create(school=self.school, name="Peer")
        endpoint = "/api/students/profile-fields/"
        created = self.client.post(endpoint, {"kind": "ID", "label": "Passport number"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        field_id = created.data["id"]
        self.assertEqual(self.client.post(endpoint, {"kind": "ID", "label": "passport NUMBER"}, format="json").status_code, 409)
        for student in [self.student, peer]:
            fields = self.client.get(f"/api/students/{student.id}/").data["custom_ids"]
            self.assertEqual(fields, [{"id": field_id, "label": created.data["label"], "value": ""}])
        saved = self.client.patch(self.url, {"custom_id_values": {str(field_id): "P123"}}, format="json")
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved.data["custom_ids"][0]["value"], "P123")
        self.assertEqual(self.client.get(f"/api/students/{peer.id}/").data["custom_ids"][0]["value"], "")
        document_field = self.client.post(endpoint, {"kind": "DOCUMENT", "label": "Medical certificate"}, format="json").data["id"]
        response = self.client.post(self.url + "documents/", {"source": "std", "profile_field": document_field, "file": self.pdf()}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["documents"][0]["profile_field"], document_field)
        self.assertEqual(self.client.get(f"/api/students/{peer.id}/").data["shared_document_fields"][0]["id"], document_field)
        self.assertEqual(self.client.post(self.url + "documents/", {"source": "std", "profile_field": document_field, "file": self.pdf()}, format="multipart").status_code, 409)
        self.client.force_authenticate(CustomUser.objects.create_user(username="other-clerk-fields", role="CLERK", school=self.other_school))
        self.assertEqual(self.client.get(f"/api/students/{self.other.id}/").data["custom_ids"], [])
        self.assertEqual(self.client.patch(f"/api/students/{self.other.id}/", {"custom_id_values": {str(field_id): "foreign"}}, format="json").status_code, 400)
        self.client.force_authenticate(CustomUser.objects.create_user(username="teacher-fields", role="TEACHER", school=self.school))
        self.assertEqual(self.client.post(endpoint, {"kind": "ID", "label": "Forbidden"}, format="json").status_code, 403)

    def test_real_list_filters_and_school_isolation(self):
        response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["completion"]["missing_documents"][0]["id"], self.slot.id)
        self.assertEqual(self.client.get("/api/students/", {"search": "GR001"}).data[0]["id"], self.student.id)
        self.assertEqual(self.client.get("/api/students/", {"division": "B"}).data, [])
        self.assertEqual(self.client.get(f"/api/students/{self.other.id}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/students/{self.other.id}/", {"abc_id": "OTHER"}, format="json").status_code, 404)

    def test_ids_persist_after_refresh_and_dynamic_values_sync(self):
        response = self.client.patch(self.url, {"aadhar_number": "012345678901", "abc_id": "ABC-001", "udise_no": "PEN-001"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.aadhar_number, "012345678901")
        self.assertEqual(self.client.get(self.url).data["abc_id"], "ABC-001")
        self.assertEqual(AdmissionFieldValue.objects.get(admission=self.admission, field=self.aadhaar_field).value, "012345678901")
        self.assertEqual(self.client.get(self.url).data["completion"]["missing_ids"], [])
        self.assertFalse(self.client.get(self.url).data["is_verified"])

    def test_invalid_aadhaar_rejected_in_all_serializer_paths(self):
        for value in ["123", "1234567890123", "12345678901A", "12345 789012", "１２３４５６７８９０１２"]:
            self.assertEqual(self.client.patch(self.url, {"aadhar_number": value}, format="json").status_code, 400)
            manual = ManualStudentSerializer(data={"school": self.school.id, "gr_no": "NEW", "aadhar_number": value})
            self.assertFalse(manual.is_valid())
            admission = AdmissionFieldValueSerializer(data={"field": self.aadhaar_field.id, "value": value})
            self.assertFalse(admission.is_valid())

    def test_upload_replace_metadata_and_delete_real_files(self):
        response = self.upload(document_type="CERTIFICATE")
        self.assertEqual(response.status_code, 201, response.data)
        document = response.data["documents"][0]
        endpoint = self.url + f"documents/{document['id']}/"
        old = StudentDocument.objects.get(pk=document["raw_id"])
        old_name, storage = old.document.name, old.document.storage
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.patch(endpoint, {"file": self.pdf("new.pdf"), "expected_file": old_name}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(StudentDocument.objects.filter(student=self.student).count(), 1)
        old.refresh_from_db()
        self.assertNotEqual(old.document.name, old_name)
        self.assertFalse(storage.exists(old_name))
        self.assertTrue(storage.exists(old.document.name))
        response = self.client.patch(endpoint, {"title": "Updated certificate", "document_type": "ACHIEVEMENT", "description": "Corrected"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.url).data["documents"][0]["title"], "updated certificate")
        new_name = old.document.name
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(endpoint, {"expected_file": new_name}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["completion"]["document_count"], 0)
        self.assertFalse(storage.exists(new_name))
        self.assertFalse(StudentDocument.objects.filter(student=self.student).exists())

    def test_admission_slot_upload_does_not_duplicate(self):
        response = self.client.post(self.url + "documents/", {"source": "adm", "document_field": self.slot.id, "file": self.pdf()}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["completion"]["missing_documents"], [])
        response = self.client.post(self.url + "documents/", {"source": "adm", "document_field": self.slot.id, "file": self.pdf()}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(AdmissionDocument.objects.filter(admission=self.admission).count(), 1)

    def test_cross_student_document_and_cross_school_slot_rejected(self):
        foreign = StudentDocument.objects.create(student=self.other, school=self.other_school, title="Foreign", document_type="OTHER", document=self.pdf())
        endpoint = self.url + f"documents/std_{foreign.id}/"
        self.assertEqual(self.client.patch(endpoint, {"title": "Attack"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(endpoint).status_code, 404)
        same_school_other = Student.objects.create(school=self.school, name="Sibling")
        own_other = StudentDocument.objects.create(student=same_school_other, school=self.school, title="Other student", document_type="OTHER", document=self.pdf())
        self.assertEqual(self.client.delete(self.url + f"documents/std_{own_other.id}/").status_code, 404)
        foreign_form = AdmissionForm.objects.bulk_create([AdmissionForm(school=self.other_school, title="External form")])[0]
        slot = DocumentField.objects.create(school=self.other_school, form=foreign_form, label="External document")
        self.assertEqual(self.client.post(self.url + "documents/", {"source": "adm", "document_field": slot.id, "file": self.pdf()}, format="multipart").status_code, 404)

    def test_verification_audit_and_revoke_use_existing_rules(self):
        response = self.client.patch(self.url, {"is_verified": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["verified_by"], self.clerk.id)
        self.assertIsNotNone(response.data["verified_at"])
        response = self.client.patch(self.url, {"abc_id": "UPDATED"}, format="json")
        self.assertTrue(response.data["is_verified"])
        response = self.client.patch(self.url, {"is_verified": False}, format="json")
        self.assertFalse(response.data["is_verified"])
        self.assertIsNone(response.data["verified_by"])

    def test_permissions_and_stale_replacement(self):
        document = self.upload().data["documents"][0]
        endpoint = self.url + f"documents/{document['id']}/"
        self.assertEqual(self.client.patch(endpoint, {"file": self.pdf(), "expected_file": "stale.pdf"}, format="multipart").status_code, 409)
        teacher = CustomUser.objects.create_user(username="profile-teacher", role="TEACHER", school=self.school)
        self.client.force_authenticate(teacher)
        self.assertEqual(self.client.patch(self.url, {"abc_id": "NO"}, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.url + "documents/").status_code, 403)
        self.assertEqual(self.client.delete(endpoint).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, [401, 403])

    def test_failed_storage_upload_keeps_existing_record_and_file(self):
        document = self.upload().data["documents"][0]
        old = StudentDocument.objects.get(pk=document["raw_id"])
        old_name = old.document.name
        self.client.raise_request_exception = False
        with patch("django.core.files.storage.FileSystemStorage.save", side_effect=OSError("Storage unavailable")):
            response = self.client.patch(self.url + f"documents/{document['id']}/", {"file": self.pdf()}, format="multipart")
        self.assertEqual(response.status_code, 500)
        old.refresh_from_db()
        self.assertEqual(old.document.name, old_name)
        self.assertTrue(old.document.storage.exists(old_name))

    def test_failed_database_update_cleans_new_file_and_keeps_original(self):
        document = self.upload().data["documents"][0]
        old = StudentDocument.objects.get(pk=document["raw_id"])
        old_name = old.document.name
        self.client.raise_request_exception = False
        with patch.object(StudentDocument, "save", side_effect=DatabaseError("Database unavailable")):
            response = self.client.patch(self.url + f"documents/{document['id']}/", {"file": self.pdf()}, format="multipart")
        self.assertEqual(response.status_code, 500)
        old.refresh_from_db()
        self.assertEqual(old.document.name, old_name)
        self.assertTrue(old.document.storage.exists(old_name))
        self.assertEqual(len(__import__('os').listdir(self.folder.name + "/student_documents")), 1)

    def test_list_queries_do_not_grow_per_student(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get("/api/students/")
        initial_count = len(queries)
        for index in range(8):
            Student.objects.create(school=self.school, school_class=self.cls, name=f"Additional {index}")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), initial_count + 1)
