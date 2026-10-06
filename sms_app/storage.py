import os
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

# Extensions that should always be uploaded and served as "raw" assets to prevent Cloudinary PDF 401 errors
RAW_DOCUMENT_EXTENSIONS = (
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp',
    '.zip', '.rar', '.tar', '.gz', '.7z'
)

try:
    from cloudinary_storage.storage import MediaCloudinaryStorage, RawMediaCloudinaryStorage
    import cloudinary
    import cloudinary.uploader

    class SmartMediaCloudinaryStorage(MediaCloudinaryStorage):
        """
        Intelligent Cloudinary storage that automatically detects non-image files
        (like PDFs, Word documents, Excel sheets, text files) and uploads /
        serves them with resource_type='raw' to avoid Cloudinary 401 Unauthorized errors.
        Images continue to use resource_type='image' for full transformation support.
        """
        def _get_resource_type(self, name):
            if not name:
                return self.RESOURCE_TYPE
            ext = os.path.splitext(name)[1].lower()
            if ext in RAW_DOCUMENT_EXTENSIONS:
                return 'raw'
            return 'image'

        def _upload(self, name, content):
            res_type = self._get_resource_type(name)
            options = {
                'use_filename': True,
                'resource_type': res_type,
                'tags': self.TAG,
            }
            folder = os.path.dirname(name)
            if folder:
                options['folder'] = folder
            return cloudinary.uploader.upload(content, **options)

        def _get_url(self, name):
            name = self._prepend_prefix(name)
            res_type = self._get_resource_type(name)
            url_options = {}
            if res_type == 'raw' or os.path.splitext(name)[1].lower() in RAW_DOCUMENT_EXTENSIONS:
                url_options['sign_url'] = True
            cloudinary_resource = cloudinary.CloudinaryResource(
                name,
                default_resource_type=res_type,
                url_options=url_options
            )
            return cloudinary_resource.url

    class SmartRawMediaCloudinaryStorage(RawMediaCloudinaryStorage):
        RESOURCE_TYPE = 'raw'

        def _get_url(self, name):
            name = self._prepend_prefix(name)
            cloudinary_resource = cloudinary.CloudinaryResource(
                name,
                default_resource_type='raw',
                url_options={'sign_url': True}
            )
            return cloudinary_resource.url

except ImportError:
    from django.core.files.storage import FileSystemStorage
    SmartMediaCloudinaryStorage = FileSystemStorage
    RawMediaCloudinaryStorage = FileSystemStorage
    SmartRawMediaCloudinaryStorage = FileSystemStorage


def get_raw_document_storage():
    """
    Returns SmartRawMediaCloudinaryStorage when Cloudinary is configured,
    or default storage otherwise. Used on model FileFields (e.g. Syllabus.syllabus_file).
    """
    if getattr(settings, 'is_cloudinary_configured', False):
        try:
            return SmartRawMediaCloudinaryStorage()
        except Exception:
            pass
    from django.core.files.storage import default_storage
    return default_storage
