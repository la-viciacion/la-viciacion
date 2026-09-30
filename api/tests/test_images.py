import io
import unittest

from PIL import Image

from src.utils.images import validate_image


def image_bytes(fmt: str, size=(8, 8)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, fmt)
    return buffer.getvalue()


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


if __name__ == "__main__":
    unittest.main()
