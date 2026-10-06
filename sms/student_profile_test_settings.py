"""Temporary isolated verification settings; removed after checks."""
from .settings import *
import tempfile
_profile_root = os.environ.get("SMS_PROFILE_TEST_ROOT", os.path.join(tempfile.gettempdir(), "sms-profile-verification"))
os.makedirs(_profile_root, exist_ok=True)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.path.join(_profile_root, "profile.sqlite3")}}
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
MEDIA_ROOT = os.path.join(_profile_root, "media")
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
DEBUG = True
MIGRATION_MODULES = {entry.split(".")[-1]: None for entry in INSTALLED_APPS if entry in {"sms_app", "sms_shared_core"} or entry.startswith("services.")}
