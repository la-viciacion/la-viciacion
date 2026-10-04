"""`.env.template` and the code must agree: every variable the code reads is in the template, and
nothing in the template is left over from code that no longer exists."""
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from src.config import Config

ROOT = Path(__file__).resolve().parents[2]

# Read by something other than our Python code, so a search of the sources cannot find them.
EXTERNAL = {
    "MARIADB_ROOT_PASSWORD",  # the MariaDB image
    "TZ",  # the containers' time zone
    "FORWARDED_ALLOW_IPS",  # uvicorn
    "DB_DATA",  # docker-compose.yml
    "LAVI_VERSION",  # docker-compose.yml (image tag)
    "API_UPSTREAM",  # docker-compose.yml, rendered into the front's nginx config
    "DNS_RESOLVER",  # same
    "FRONT_HOST_IP", "FRONT_HOST_PORT", "API_HOST_IP", "API_HOST_PORT", "DB_HOST_IP", "DB_HOST_PORT",  # docker-compose.yml (published ports)
}
# Set when the image is built (a build arg of release.yml), not by whoever deploys it.
BAKED = {"APP_VERSION"}
# Only read to seed the settings the first time, or kept so an old .env keeps working.
LEGACY = {"OPENAI_API_KEY", "OPENAI_MODEL", "RAWG_URL"}

READ = re.compile(
    r"(?:getenv|_get_env|_get_env_json)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']|environ\[\s*[\"']([A-Z][A-Z0-9_]*)[\"']\]"
)
SEEDS = re.compile(r"env=\"([A-Z][A-Z0-9_]*)\"")


def template_variables() -> set[str]:
    text = (ROOT / ".env.template").read_text(encoding="utf-8")
    return set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", text, re.MULTILINE))


def variables_read() -> set[str]:
    found = set()
    for folder in ("api/src", "bot/src"):
        for path in (ROOT / folder).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            found |= {a or b for a, b in READ.findall(source)}
            found |= set(SEEDS.findall(source))
    return found


class TemplateAgreesWithTheCodeTests(unittest.TestCase):
    def test_every_variable_the_code_reads_is_in_the_template(self):
        missing = variables_read() - template_variables() - LEGACY - BAKED  # the old names are explained in a comment
        self.assertEqual(missing, set(), "read by the code but missing from .env.template")

    def test_nothing_in_the_template_is_left_over(self):
        leftovers = template_variables() - variables_read() - EXTERNAL - LEGACY
        self.assertEqual(leftovers, set(), "in .env.template but nobody reads it")


class AppVersionTests(unittest.TestCase):
    def version(self, **env):
        with mock.patch.dict(os.environ, env, clear=True):
            return object.__new__(Config).APP_VERSION

    def test_it_is_dev_unless_the_image_was_built_with_a_release(self):
        self.assertEqual(self.version(), "dev")
        self.assertEqual(self.version(APP_VERSION=""), "dev")
        self.assertEqual(self.version(APP_VERSION="2.1.0"), "2.1.0")


class RawgKeyTests(unittest.TestCase):
    def key(self, **env):
        config = object.__new__(Config)
        config.RAWG_URL = env.pop("RAWG_URL", "")
        clean = {k: v for k, v in os.environ.items() if k != "RAWG_API_KEY"}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            return config.RAWG_API_KEY

    def test_the_key_variable_is_used(self):
        self.assertEqual(self.key(RAWG_API_KEY=" abc "), "abc")

    def test_the_key_variable_wins_over_the_old_url(self):
        self.assertEqual(self.key(RAWG_API_KEY="new", RAWG_URL="https://api.rawg.io/api/games?key=old&page=1"), "new")

    def test_an_old_env_with_only_the_url_keeps_working(self):
        self.assertEqual(self.key(RAWG_URL="https://api.rawg.io/api/games?key=old&page=1&search="), "old")

    def test_no_key_at_all_is_an_empty_string(self):
        self.assertEqual(self.key(), "")


if __name__ == "__main__":
    unittest.main()
