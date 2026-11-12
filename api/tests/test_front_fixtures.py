"""The front's tests load real answers of the API (tests/front_fixtures.py): they must be the current ones."""
import unittest

from src.utils import settings
from tests import front_fixtures


class FrontFixturesTests(unittest.TestCase):
    def test_the_saved_answers_are_up_to_date(self):
        for name, env in front_fixtures.SCENARIOS.items():
            saved = (front_fixtures.TARGET / name).read_text(encoding="utf-8")
            self.assertEqual(saved, front_fixtures.render(front_fixtures.build(env)), f"{name} is out of date: run `python -m tests.front_fixtures` from api/")

    def test_every_setting_is_in_the_answer(self):
        payload = front_fixtures.build({})
        self.assertEqual(set(payload["values"]), set(settings.REGISTRY))
        self.assertEqual({"values", "jobs", "push_devices", "mail", "games_sources", "ai_uses", "ai_model", "ai_providers", "chat", "guide"}, set(payload))


if __name__ == "__main__":
    unittest.main()
