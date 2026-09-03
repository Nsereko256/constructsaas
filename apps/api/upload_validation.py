from pathlib import Path

from rest_framework.exceptions import ValidationError


MAX_IMAGE_UPLOAD_BYTES = 1024 * 1024
IMAGE_EXTENSIONS = {'.bmp', '.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp'}


def validate_image_upload(uploaded_file):
    """Reject images larger than 1 MiB, including renamed image files."""
    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    extension = Path(getattr(uploaded_file, 'name', '')).suffix.lower()
    if (content_type.startswith('image/') or extension in IMAGE_EXTENSIONS) and uploaded_file.size > MAX_IMAGE_UPLOAD_BYTES:
        raise ValidationError({'file': ['Images must be 1 MB or smaller.']})
    return uploaded_file
