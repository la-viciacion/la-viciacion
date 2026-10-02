import datetime
import unittest

from fastapi import HTTPException

from src.database import models
from src.routers import manage
from tests.sqlite_db import make_session


class PlatformIdTests(unittest.TestCase):
    def test_ids_are_readable_and_url_safe(self):
        self.assertEqual(manage.platform_id_for("PlayStation 5", set()), "playstation-5")
        self.assertEqual(manage.platform_id_for("  Nintendo   Switch 2 ", set()), "nintendo-switch-2")
        self.assertEqual(manage.platform_id_for("Móvil (Android)", set()), "movil-android")

    def test_a_name_with_no_usable_letters_still_gets_an_id(self):
        self.assertEqual(manage.platform_id_for("🎮🎮", set()), "platform")

    def test_a_taken_id_gets_a_number(self):
        self.assertEqual(manage.platform_id_for("PC", {"pc"}), "pc-2")
        self.assertEqual(manage.platform_id_for("PC", {"pc", "pc-2"}), "pc-3")


class PlatformsAdminTests(unittest.TestCase):
    def refused(self, call, status):
        with self.assertRaises(HTTPException) as ctx:
            call()
        self.assertEqual(ctx.exception.status_code, status, ctx.exception.detail)
        return ctx.exception.detail

    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.PlatformTag(id="pc", name="PC"), models.PlatformTag(id="ps5", name="PlayStation 5"), models.Game(id="g", name="Doom")])
        start = datetime.datetime(2026, 3, 1, 10)
        self.db.add(models.GameTimer(user_id=1, game_id="g", platform="pc", start_time=start, end_time=start, duration_seconds=0, is_active=False))
        self.db.add(models.GameTimer(user_id=1, game_id="g", platform="pc", start_time=start + datetime.timedelta(days=1), is_active=False))
        self.db.add(models.UserGame(user_id=1, game_id="g", platform="pc", started_date=start.date(), completed=0))
        self.db.commit()

    def test_the_list_shows_usage_sorted_by_name(self):
        got = manage.list_platforms(self.db)
        self.assertEqual([(p["name"], p["sessions"], p["library"]) for p in got], [("PC", 2, 1), ("PlayStation 5", 0, 0)])

    def test_create_makes_an_id_from_the_name(self):
        created = manage.create_platform(manage.PlatformBody(name=" Nintendo Switch 2 "), self.db)
        self.assertEqual((created["id"], created["name"]), ("nintendo-switch-2", "Nintendo Switch 2"))
        self.assertIsNotNone(self.db.get(models.PlatformTag, "nintendo-switch-2"))

    def test_a_name_that_exists_is_refused_whatever_its_case(self):
        self.refused(lambda: manage.create_platform(manage.PlatformBody(name="pc"), self.db), 409)

    def test_names_must_be_filled_and_not_too_long(self):
        self.refused(lambda: manage.create_platform(manage.PlatformBody(name="   "), self.db), 400)
        self.refused(lambda: manage.create_platform(manage.PlatformBody(name="x" * 101), self.db), 400)

    def test_rename_keeps_the_id_so_sessions_follow(self):
        manage.patch_platform("pc", manage.PlatformBody(name="Ordenador"), self.db)
        self.assertEqual(self.db.get(models.PlatformTag, "pc").name, "Ordenador")
        self.assertEqual(self.db.query(models.GameTimer).filter_by(platform="pc").count(), 2)

    def test_renaming_to_its_own_name_is_fine_but_not_to_another_ones(self):
        manage.patch_platform("pc", manage.PlatformBody(name="PC"), self.db)
        self.refused(lambda: manage.patch_platform("pc", manage.PlatformBody(name="playstation 5"), self.db), 409)

    def test_an_unknown_platform_is_a_404(self):
        self.refused(lambda: manage.patch_platform("nope", manage.PlatformBody(name="X"), self.db), 404)
        self.refused(lambda: manage.delete_platform("nope", self.db), 404)

    def test_an_unused_platform_can_be_deleted(self):
        manage.delete_platform("ps5", self.db)
        self.assertIsNone(self.db.get(models.PlatformTag, "ps5"))

    def test_a_platform_in_use_is_refused_and_says_by_what(self):
        detail = self.refused(lambda: manage.delete_platform("pc", self.db), 409)
        self.assertIn("2 sesiones", detail)
        self.assertIn("1 biblioteca", detail)
        self.assertIsNotNone(self.db.get(models.PlatformTag, "pc"))


if __name__ == "__main__":
    unittest.main()
