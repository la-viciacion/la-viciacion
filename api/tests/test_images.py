import io
import unittest

from PIL import Image

from src.utils import messages
from src.utils.images import media_type_of, normalize_image, upload_error, validate_image


def image_bytes(fmt: str, size=(8, 8), mode="RGB", **save) -> bytes:
    buffer = io.BytesIO()
    Image.new(mode, size, "red").save(buffer, fmt, **save)
    return buffer.getvalue()


def opened(data: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    image.load()
    return image


class ValidateImageTests(unittest.TestCase):
    def test_accepts_png_and_jpeg(self):
        self.assertEqual(validate_image(image_bytes("PNG"), 10_000), "image/png")
        self.assertEqual(validate_image(image_bytes("JPEG"), 10_000), "image/jpeg")

    def test_rejects_other_image_formats(self):
        for fmt in ("GIF", "WEBP", "BMP"):
            with self.assertRaisesRegex(ValueError, "type"):
                validate_image(image_bytes(fmt), 10_000)

    def test_rejects_non_images_even_if_the_content_type_lied(self):
        for data in (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", b"GIF89a....", b"not an image"):
            with self.assertRaisesRegex(ValueError, "type"):
                validate_image(data, 10_000)

    def test_rejects_truncated_files(self):
        with self.assertRaises(ValueError):
            validate_image(image_bytes("PNG")[:40], 10_000)

    def test_rejects_empty_and_oversized(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_image(b"", 10_000)
        with self.assertRaisesRegex(ValueError, "too_big"):
            validate_image(image_bytes("PNG"), 10)

    def test_rejects_huge_dimensions(self):
        with self.assertRaisesRegex(ValueError, "too_big"):
            validate_image(image_bytes("PNG", size=(5000, 5000)), 10_000_000)


class NormalizeImageTests(unittest.TestCase):
    def test_a_big_image_is_scaled_down_keeping_its_format(self):
        for fmt, media in (("PNG", "image/png"), ("JPEG", "image/jpeg")):
            with self.subTest(fmt=fmt):
                data = normalize_image(image_bytes(fmt, size=(1024, 1024)), 256)
                self.assertEqual((opened(data).size, media_type_of(data)), ((256, 256), media))

    def test_a_small_image_is_not_enlarged(self):
        self.assertEqual(opened(normalize_image(image_bytes("PNG", size=(40, 40)), 256)).size, (40, 40))

    def test_proportions_are_kept_when_it_is_not_square(self):
        self.assertEqual(opened(normalize_image(image_bytes("PNG", size=(800, 400)), 256)).size, (256, 128))

    def test_it_ends_up_much_smaller_than_the_upload(self):
        noisy = Image.effect_noise((1024, 1024), 80).convert("RGB")
        buffer = io.BytesIO()
        noisy.save(buffer, "JPEG", quality=100)
        self.assertLess(len(normalize_image(buffer.getvalue(), 256)), len(buffer.getvalue()) // 10)

    def test_transparency_survives(self):
        data = normalize_image(image_bytes("PNG", size=(600, 600), mode="RGBA"), 512)
        self.assertEqual((opened(data).mode, opened(data).size), ("RGBA", (512, 512)))

    def test_a_palette_makes_a_png_much_smaller_and_keeps_its_transparency(self):
        noisy = Image.effect_noise((300, 300), 60).convert("RGBA")
        noisy.paste((0, 0, 0, 0), (0, 0, 20, 20))
        buffer = io.BytesIO()
        noisy.save(buffer, "PNG")
        plain = normalize_image(buffer.getvalue(), 512)
        reduced = normalize_image(buffer.getvalue(), 512, palette=True)
        self.assertLess(len(reduced), len(plain))
        small = opened(reduced).convert("RGBA")
        self.assertEqual((small.getpixel((5, 5))[3], small.getpixel((150, 150))[3]), (0, 255))

    def test_a_palette_png_with_transparency_keeps_it(self):
        buffer = io.BytesIO()
        Image.new("P", (10, 10)).save(buffer, "PNG", transparency=0)
        self.assertEqual(opened(normalize_image(buffer.getvalue(), 512)).mode, "RGBA")

    def test_metadata_is_dropped(self):
        exif = Image.Exif()
        exif[0x010F] = "SomeCamera"
        data = normalize_image(image_bytes("JPEG", size=(64, 64), exif=exif), 256)
        self.assertEqual(len(opened(data).getexif()), 0)

    def test_the_exif_rotation_is_applied_before_it_is_dropped(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotated 90 degrees: displayed as 100 wide by 200 tall
        data = normalize_image(image_bytes("JPEG", size=(200, 100), exif=exif), 512)
        self.assertEqual(opened(data).size, (100, 200))

    def test_the_same_errors_as_the_validation(self):
        with self.assertRaisesRegex(ValueError, "type"):
            normalize_image(image_bytes("GIF"), 256)
        with self.assertRaisesRegex(ValueError, "too_big"):
            normalize_image(image_bytes("PNG", size=(5000, 5000)), 256, max_bytes=10_000_000)
        with self.assertRaisesRegex(ValueError, "empty"):
            normalize_image(b"", 256)

    def test_corrupt_pixel_data_is_refused_not_a_500(self):
        data = image_bytes("PNG", size=(300, 300))
        with self.assertRaises(ValueError):
            normalize_image(data[: len(data) - 20] + b"\0" * 20, 256)


class UploadErrorTests(unittest.TestCase):
    def test_messages_are_the_spanish_ones(self):
        self.assertEqual(upload_error(ValueError("type")), messages.FILE_TYPE_NOT_ALLOWED)
        self.assertEqual(upload_error(ValueError("empty")), messages.FILE_TYPE_NOT_ALLOWED)
        self.assertIn("5 MB", upload_error(ValueError("too_big")))


if __name__ == "__main__":
    unittest.main()


class MediaTypeOfTests(unittest.TestCase):
    def test_png_and_jpeg_are_told_apart(self):
        self.assertEqual(media_type_of(b"\x89PNG\r\n\x1a\n...."), "image/png")
        self.assertEqual(media_type_of(b"\xff\xd8\xff\xe0...."), "image/jpeg")
