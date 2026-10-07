import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from src.crud import users  # noqa: F401  (the app's modules import each other: this order is the one that resolves)
from src.database import models
from src.utils import achievement_images as store
from src.utils import images
from src.utils.achievements import AchievementsElems
from tests.sqlite_db import make_session


def png(size=64, color=(200, 30, 30, 255)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (size, size), color).save(out, "PNG")
    return out.getvalue()


def jpg(size=64) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (size, size), (10, 120, 200)).save(out, "JPEG")
    return out.getvalue()


def noisy_png(size: int = 200) -> bytes:
    out = io.BytesIO()
    Image.effect_noise((size, size), 40).convert("RGBA").save(out, "PNG")
    return out.getvalue()


class LoadIntoDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Achievement(id=1, key="ONE", title="One", message="x"),
            models.Achievement(id=2, key="TWO", title="Two", message="x"),
        ])
        self.db.commit()
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.folder = Path(self.dir.name)

    def put(self, name, data):
        (self.folder / name).write_bytes(data)

    def image(self, key):
        return self.db.query(models.Achievement.image).filter_by(key=key).scalar()

    def load(self):
        return store.load_into_database(self.db, self.folder)

    def test_a_file_is_loaded_as_an_upload_from_the_panel_would_be(self):
        big = png(size=1200)
        self.put("ONE.png", big)
        self.assertEqual(self.load(), {"loaded": 1, "unchanged": 0, "skipped": 0})
        self.assertEqual(bytes(self.image("ONE")), images.normalize_image(big, images.ACHIEVEMENT_MAX_SIDE, palette=True))
        with Image.open(io.BytesIO(bytes(self.image("ONE")))) as stored:
            self.assertEqual(stored.size, (images.ACHIEVEMENT_MAX_SIDE, images.ACHIEVEMENT_MAX_SIDE))

    def test_a_jpg_is_loaded_too_and_keeps_its_format(self):
        self.put("TWO.jpg", jpg())
        self.load()
        self.assertEqual(images.media_type_of(bytes(self.image("TWO"))), "image/jpeg")

    def test_a_start_that_changes_nothing_writes_nothing(self):
        self.put("ONE.png", png())
        self.load()
        self.assertEqual(self.load(), {"loaded": 0, "unchanged": 1, "skipped": 0})

    def test_replacing_the_file_replaces_the_picture_at_the_next_start(self):
        self.put("ONE.png", png(color=(1, 2, 3, 255)))
        self.load()
        first = bytes(self.image("ONE"))
        self.put("ONE.png", png(color=(250, 250, 0, 255)))
        self.assertEqual(self.load()["loaded"], 1)
        self.assertNotEqual(bytes(self.image("ONE")), first)

    def test_the_file_wins_over_a_picture_uploaded_by_hand(self):
        self.db.query(models.Achievement).filter_by(key="ONE").update({"image": b"uploaded in the panel"})
        self.db.commit()
        self.put("ONE.png", png())
        self.load()
        self.assertNotEqual(bytes(self.image("ONE")), b"uploaded in the panel")

    def test_an_achievement_without_a_file_is_not_touched(self):
        self.db.query(models.Achievement).filter_by(key="TWO").update({"image": b"uploaded in the panel"})
        self.db.commit()
        self.put("ONE.png", png())
        self.load()
        self.assertEqual(bytes(self.image("TWO")), b"uploaded in the panel")

    def test_a_file_with_no_achievement_is_skipped(self):
        self.put("NOPE.png", png())
        self.assertEqual(self.load(), {"loaded": 0, "unchanged": 0, "skipped": 1})

    def test_two_files_for_one_key_are_not_used(self):
        self.put("ONE.png", png())
        self.put("ONE.jpg", jpg())
        self.assertEqual(self.load(), {"loaded": 0, "unchanged": 0, "skipped": 1})
        self.assertIsNone(self.image("ONE"))

    def test_a_broken_file_is_skipped_and_the_others_still_load(self):
        self.put("ONE.png", b"not a picture")
        self.put("TWO.png", png())
        self.assertEqual(self.load(), {"loaded": 1, "unchanged": 0, "skipped": 1})
        self.assertIsNone(self.image("ONE"))
        self.assertIsNotNone(self.image("TWO"))

    def test_other_files_and_a_missing_folder_are_ignored(self):
        self.put("README.md", b"# notes")
        nothing = {"loaded": 0, "unchanged": 0, "skipped": 0}
        self.assertEqual(self.load(), nothing)
        self.assertEqual(store.load_into_database(self.db, self.folder / "nowhere"), nothing)


class CompressForDiskTests(unittest.TestCase):
    def test_a_png_gets_smaller_at_the_same_size(self):
        data = noisy_png()
        small = store.compress_for_disk(data)
        self.assertLess(len(small), len(data))
        with Image.open(io.BytesIO(small)) as image:
            self.assertEqual((image.format, image.size), ("PNG", (200, 200)))

    def test_a_big_picture_is_scaled_down_and_a_small_one_is_never_enlarged(self):
        with Image.open(io.BytesIO(store.compress_for_disk(noisy_png(size=900)))) as big:
            self.assertEqual(big.size, (images.ACHIEVEMENT_MAX_SIDE, images.ACHIEVEMENT_MAX_SIDE))
        with Image.open(io.BytesIO(store.compress_for_disk(noisy_png(size=100)))) as small:
            self.assertEqual(small.size, (100, 100))

    def test_a_transparent_corner_stays_transparent(self):
        base = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        base.paste(Image.new("RGBA", (32, 32), (255, 0, 0, 255)), (16, 16))
        out = io.BytesIO()
        base.save(out, "PNG")
        with Image.open(io.BytesIO(store.compress_for_disk(out.getvalue()))) as small:
            small = small.convert("RGBA")
            self.assertEqual(small.getpixel((0, 0))[3], 0)
            self.assertEqual(small.getpixel((32, 32))[3], 255)

    def test_what_is_already_small_is_never_made_bigger(self):
        data = png(size=8)
        self.assertLessEqual(len(store.compress_for_disk(data)), len(data))

    def test_a_jpeg_stays_a_jpeg_and_does_not_grow(self):
        out = io.BytesIO()
        Image.effect_noise((300, 300), 60).convert("RGB").save(out, "JPEG", quality=100)
        small = store.compress_for_disk(out.getvalue())
        self.assertEqual(images.media_type_of(small), "image/jpeg")
        self.assertLessEqual(len(small), len(out.getvalue()))

    def test_it_is_still_a_picture_the_loader_accepts(self):
        small = store.compress_for_disk(noisy_png())
        self.assertTrue(images.normalize_image(small, images.ACHIEVEMENT_MAX_SIDE))

    def test_the_folder_command_shrinks_the_files_in_place(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ONE.png"
            path.write_bytes(noisy_png())
            before, after = store.compress_folder(Path(folder))
            self.assertLess(after, before)
            self.assertEqual(path.stat().st_size, after)


class TheFolderOfTheRepositoryTests(unittest.TestCase):
    """Guards for the files that are really in api/achievement_images."""

    def test_every_file_is_a_valid_picture_named_after_an_achievement_key(self):
        files, repeated = store.files_by_key()
        keys = {a.name for a in AchievementsElems}
        self.assertEqual(repeated, [])
        self.assertGreater(len(files), 0)
        for key, path in files.items():
            with self.subTest(file=path.name):
                self.assertIn(key, keys)
                self.assertTrue(images.normalize_image(path.read_bytes(), images.ACHIEVEMENT_MAX_SIDE))

    def test_nothing_else_is_in_the_folder_but_pictures_and_its_readme(self):
        others = [p.name for p in store.IMAGES_DIR.iterdir() if p.suffix.lower() not in store.EXTENSIONS and p.name != "README.md"]
        self.assertEqual(others, [])

    def test_the_folder_is_small_enough_for_the_repository(self):
        self.assertLess(sum(p.stat().st_size for p in store.IMAGES_DIR.iterdir()), 8 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
