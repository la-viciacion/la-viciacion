"""The pictures of the achievements, kept on disk (`api/achievement_images/<KEY>.png|jpg`) and loaded into the
database every time the API starts.

The folder is the original of each picture: the database only holds what the app serves. A picture is replaced by
dropping a new file with the name of the achievement's key, and it is in the app after the next start. At start
each file is put through `images.normalize_image`, exactly what an upload from the admin panel goes through (shrunk
to `ACHIEVEMENT_MAX_SIDE`, re-encoded without metadata), and is only written when it differs from what the database
already has, so a start that changes nothing writes nothing.

**The file wins**: an achievement that has a file gets that picture at every start, replacing one uploaded by hand
in the panel. An achievement without a file is not touched. A file that cannot be read, that names no achievement
or that is there twice (`X.png` and `X.jpg`) is logged and skipped: the API never fails to start because of a picture.

`python -m src.utils.achievement_images` shrinks the files of the folder in place (see `compress_for_disk`) so the
repository does not carry megabytes: run it after adding or replacing a picture.
"""
import io
import sys
from pathlib import Path

from PIL import Image
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import models
from . import images
from .logger import LogManager

logger = LogManager().get_logger()

IMAGES_DIR = Path(__file__).resolve().parents[2] / "achievement_images"
EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PALETTE_COLORS = 256


def files_by_key(directory: Path = IMAGES_DIR) -> tuple[dict[str, Path], list[str]]:
    """key -> file of the folder, and the keys that have more than one file (those are not used)."""
    found: dict[str, list[Path]] = {}
    if directory.is_dir():
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                found.setdefault(path.stem, []).append(path)
    return {key: paths[0] for key, paths in found.items() if len(paths) == 1}, [k for k, p in found.items() if len(p) > 1]


def load_into_database(db: Session, directory: Path = IMAGES_DIR) -> dict:
    """Put the pictures of the folder in the database (see the module's docstring). Returns what it did."""
    report = {"loaded": 0, "unchanged": 0, "skipped": 0}
    files, repeated = files_by_key(directory)
    for key in repeated:
        logger.warning(f"Achievement image {key}: more than one file in {directory.name}, none is used")
        report["skipped"] += 1
    if not files:
        return report
    stored = {key: bytes(image) if image is not None else None
              for key, image in db.query(models.Achievement.key, models.Achievement.image).filter(models.Achievement.key.in_(files))}
    for key, path in files.items():
        if key not in stored:
            logger.warning(f"Achievement image {path.name}: there is no achievement with the key {key}")
            report["skipped"] += 1
            continue
        try:
            data = images.normalize_image(path.read_bytes(), images.ACHIEVEMENT_MAX_SIDE)
        except (ValueError, OSError) as e:
            logger.error(f"Achievement image {path.name} cannot be used: {e}")
            report["skipped"] += 1
            continue
        if data == stored[key]:
            report["unchanged"] += 1
            continue
        db.execute(update(models.Achievement).where(models.Achievement.key == key).values(image=data))
        report["loaded"] += 1
    db.commit()
    return report


def compress_for_disk(data: bytes) -> bytes:
    """A smaller encoding of the same picture, at the same size, for the repository. A PNG is reduced to a palette
    of 256 colours with dithering (the pictures are illustrations: the difference is not visible and the file ends
    up a sixth of the size), transparency kept; a JPEG is encoded again at quality 85. What is not smaller is
    returned as it came."""
    media_type = images.validate_image(data, max_bytes=len(data))
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        out = io.BytesIO()
        if media_type == "image/png":
            if "A" in source.getbands() or "transparency" in source.info:
                # the octree method keeps the alpha channel, and is also the one that gives the smallest file
                palette = source.convert("RGBA").quantize(PALETTE_COLORS, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)
            else:
                palette = source.convert("RGB").quantize(PALETTE_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
            palette.save(out, "PNG", optimize=True)
        else:
            source.convert("RGB").save(out, "JPEG", quality=images.JPEG_QUALITY, optimize=True)
    smaller = out.getvalue()
    return smaller if len(smaller) < len(data) else data


def compress_folder(directory: Path = IMAGES_DIR) -> tuple[int, int]:
    """Shrink every file of the folder in place; returns the bytes before and after."""
    before = after = 0
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS):
        data = path.read_bytes()
        smaller = compress_for_disk(data)
        before += len(data)
        after += len(smaller)
        if smaller is not data:
            path.write_bytes(smaller)
    return before, after


if __name__ == "__main__":
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else IMAGES_DIR
    done_before, done_after = compress_folder(folder)
    print(f"{done_before / 1024 / 1024:.1f} MB -> {done_after / 1024 / 1024:.1f} MB")
