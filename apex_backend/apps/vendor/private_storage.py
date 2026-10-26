import os
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class VendorVerificationStorage(FileSystemStorage):
    def __init__(self, location=None, base_url=None):
        private_root = location or os.environ.get(
            'PRIVATE_UPLOAD_ROOT',
            str(Path(settings.BASE_DIR) / 'private_uploads'),
        )
        super().__init__(
            location=private_root,
            base_url=base_url,
            file_permissions_mode=0o600,
            directory_permissions_mode=0o700,
        )


vendor_verification_storage = VendorVerificationStorage()
