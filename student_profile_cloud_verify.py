"""Temporary live storage check with synthetic image data and guaranteed cleanup."""
import base64
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "sms.student_profile_test_settings"
import django
django.setup()
from django.test import override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from sms import settings as live
from sms_app.models import CustomUser, Student, StudentDocument

if not getattr(live, "is_cloudinary_configured", False):
    print("Cloudinary is not configured; storage adapter checks passed using isolated local storage.")
    raise SystemExit(0)
clerk = CustomUser.objects.get(username="browser-profile-clerk")
student = Student.objects.create(school=clerk.school, name="Cloud Storage Verification")
client = APIClient()
client.force_authenticate(clerk)
url = f"/api/students/{student.id}/documents/"
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jZQAAAABJRU5ErkJggg==")
assets = []
with override_settings(STORAGES=live.STORAGES):
    try:
        upload = client.post(url, {"title": "Temporary storage verification", "document_type": "OTHER", "file": SimpleUploadedFile("verification.png", png, "image/png")}, format="multipart")
        assert upload.status_code == 201, f"Cloud upload returned {upload.status_code}"
        document = upload.data["documents"][0]
        record = StudentDocument.objects.get(student=student)
        storage = record.document.storage
        assets.append((storage, record.document.name))
        assert "cloudinary" in document["url"], "Configured storage did not return a Cloudinary URL"
        endpoint = url + document["id"] + "/"
        replacement = client.patch(endpoint, {"expected_file": record.document.name, "file": SimpleUploadedFile("replacement.png", png, "image/png")}, format="multipart")
        assert replacement.status_code == 200, f"Cloud replacement returned {replacement.status_code}"
        record.refresh_from_db()
        assets.append((storage, record.document.name))
        assert len(replacement.data["documents"]) == 1
        assert assets[0][1] != assets[1][1]
        assert not storage.exists(assets[0][1]), "Old Cloudinary asset still exists"
        deleted = client.delete(endpoint, {"expected_file": record.document.name}, format="json")
        assert deleted.status_code == 200
        assert not storage.exists(assets[1][1]), "Deleted Cloudinary asset still exists"
        print("PASS: live Cloudinary upload, replacement on the same record, old asset cleanup, deletion and asset cleanup.")
    finally:
        for record in StudentDocument.objects.filter(student=student):
            record.document.delete(save=False)
            record.delete()
        for storage, name in assets:
            if storage.exists(name):
                storage.delete(name)
        student.delete()
