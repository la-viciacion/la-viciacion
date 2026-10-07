"""Validation and normalisation of uploaded images (avatars, achievement images).

What is stored is never the upload itself: `normalize_image` shrinks it to a maximum side and encodes it again
without metadata, so the database keeps the least that serves the screen and no EXIF (GPS, camera) survives.
"""
import hashlib
import io

from fastapi import Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from src.utils import messages

ALLOWED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # what may be sent; what is stored is far smaller
MAX_PIXELS = 16_000_000  # refuses decompression bombs before decoding anything
AVATAR_MAX_SIDE = 256
ACHIEVEMENT_MAX_SIDE = 256  # an icon shown at 56 px; also what the repository keeps on disk
PALETTE_COLORS = 256
JPEG_QUALITY = 85


def media_type_of(data: bytes) -> str:
    """Media type of an image that was validated when it was uploaded (only PNG or JPEG get in)."""
    return "image/png" if data.startswith(b"\x89PNG") else "image/jpeg"


def cached_image(request: Request, data: bytes, cache_control: str) -> Response:
    """The stored image, or a 304 when the browser already has this exact one (its ETag is a hash of the bytes):
    the picture is only sent again when it changed."""
    etag = '"' + hashlib.sha1(data).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": cache_control}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=media_type_of(data), headers=headers)


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


def upload_error(error: ValueError) -> str:
    """The user-facing message of a `ValueError` raised by `validate_image` / `normalize_image`."""
    if str(error) == "too_big":
        return messages.FILE_TOO_BIG.format(mb=MAX_UPLOAD_BYTES // (1024 * 1024), mp=MAX_PIXELS // 1_000_000)
    return messages.FILE_TYPE_NOT_ALLOWED


def _mode_to_keep(image: Image.Image) -> str:
    """The colour mode to re-encode in: transparency is kept, anything exotic (palette, CMYK, 16 bit) becomes RGB."""
    if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
        return "RGBA"
    return image.mode if image.mode in ("L", "RGB") else "RGB"


def _to_palette(image: Image.Image) -> Image.Image:
    """The picture with at most PALETTE_COLORS colours, dithered, transparency kept. For illustrations (logos,
    icons) the difference is not visible and the PNG ends up a fraction of the size; not for photos."""
    if image.mode == "L":
        return image  # at most 256 greys already
    # one that already has few enough colours is kept exactly: no dithering, so a picture that was reduced before
    # does not lose anything more each time it goes through here
    dither = Image.Dither.NONE if image.getcolors(PALETTE_COLORS) is not None else Image.Dither.FLOYDSTEINBERG
    # the octree method keeps the alpha channel, and is also the one that gives the smallest file
    method = Image.Quantize.FASTOCTREE if image.mode == "RGBA" else Image.Quantize.MEDIANCUT
    return image.quantize(PALETTE_COLORS, method=method, dither=dither)


def normalize_image(data: bytes, max_side: int, max_bytes: int = MAX_UPLOAD_BYTES, palette: bool = False) -> bytes:
    """Validate `data` (same errors as `validate_image`) and return it scaled down to fit in `max_side` x `max_side`
    (never enlarged, proportions kept: the uploader supplies a square one) and encoded again without metadata.
    The format is kept: PNG stays PNG (with its transparency), JPEG stays JPEG. With `palette` a PNG is also
    reduced to a palette of colours (see `_to_palette`): only for illustrations."""
    media_type = validate_image(data, max_bytes)
    try:
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)  # a phone photo's rotation lives in the EXIF that is dropped
            image = image.convert(_mode_to_keep(image))
    except (OSError, SyntaxError):  # truncated or corrupt pixel data that `verify` does not see
        raise ValueError("type")
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    if media_type == "image/png":
        (_to_palette(image) if palette else image).save(out, "PNG", optimize=True)
    else:
        image.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()
