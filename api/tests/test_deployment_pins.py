"""The images the stack runs name an exact version, so what is tested is what is deployed.

A tag that moves (`mariadb`, `nginx:alpine`, `latest`) lets a pull change the database or the web server
without any change in the repository. For MariaDB it is also dangerous: a data directory cannot be
opened by an older server (docs/deployment.md#mariadb-version). CI reads the MariaDB tag from
docker-compose.yml to decide which server to test on, so it has to be there and has to be explicit.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPLICIT_MARIADB = re.compile(r"^mariadb:\d+\.\d+(\.\d+)?$")
EXPLICIT_BASE_IMAGE = re.compile(r"^FROM \S+:\d")


def compose_mariadb_images() -> list[str]:
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    return re.findall(r"^\s*image:\s*(mariadb\S*)\s*$", text, re.MULTILINE)


class ImagesArePinnedTests(unittest.TestCase):
    def test_the_compose_file_names_one_mariadb_image_with_a_version(self):
        images = compose_mariadb_images()
        self.assertEqual(len(images), 1, f"expected one mariadb image in docker-compose.yml, found {images}")
        self.assertRegex(images[0], EXPLICIT_MARIADB, "pin it to a version, e.g. mariadb:12.3.3 (not latest, lts or no tag)")

    def test_the_development_override_leaves_the_database_image_alone(self):
        override = (ROOT / "docker-compose.dev.yml").read_text(encoding="utf-8")
        self.assertNotRegex(override, r"image:\s*mariadb", "the dev stack must run the same MariaDB as the main one")

    def test_every_dockerfile_starts_from_a_versioned_image(self):
        dockerfiles = sorted(ROOT.glob("*/Dockerfile"))
        self.assertTrue(dockerfiles)
        for dockerfile in dockerfiles:
            with self.subTest(dockerfile=dockerfile.parent.name):
                first = next(l for l in dockerfile.read_text(encoding="utf-8").splitlines() if l.startswith("FROM "))
                self.assertRegex(first, EXPLICIT_BASE_IMAGE)
                self.assertNotIn(":latest", first)
