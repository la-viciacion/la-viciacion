"""Validation of uploaded images (avatars, achievement images)."""
import io

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}
MAX_PIXELS = 16_000_000  # refuses decompression bombs before decoding anything


def media_type_of(data: bytes) -> str:
    """Media type of an image that was validated when it was uploaded (only PNG or JPEG get in)."""
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def validate_image(data: bytes, max_bytes: int) -> str:
    """Return the media type of `data` or raise ValueError with a user-facing reason.

    The declared content type of an upload is client-controlled, so the bytes
    themselves are checked: they must be a well-formed PNG or JPEG of sane size.
    """
    if not data:
        raise ValueError("empty")
    if len(data) > max_bytes:
        raise ValueError("too_big")
    try:
        with Image.open(io.BytesIO(data)) as image:
            media_type = ALLOWED_FORMATS.get(image.format)
            if media_type is None:
                raise ValueError("type")
            width, height = image.size
            if width * height > MAX_PIXELS:
                raise ValueError("too_big")
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("type")
    return media_type
