"""The users router through real requests: accounts, profile, settings, password, library, completions and
avatars (MariaDB required, see api_support.py)."""
import datetime
import io
from datetime import timedelta

from PIL import Image
from sqlalchemy import text

from src.utils import messages, seasons
from tests.api_support import PASSWORD, ApiTestCase

NEW_PASSWORD = "An0ther-secret!pw"
TODAY = datetime.date.today


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


def png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buffer, "PNG")
    return buffer.getvalue()


def gif() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, "GIF")
    return buffer.getvalue()


class UsersTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana", email="ana@example.com", telegram_id=111)
        self.bea = self.user("bea", email="bea@example.com")
        self.root = self.user("root", admin=True, email="root@example.com")
        for game_id in ("celeste", "hades", "tetris"):
            self.game(game_id)


class AccountsTests(UsersTestCase):
    def test_only_an_admin_lists_the_users_and_never_the_emergency_account_or_the_disabled(self):
        self.user("admin", admin=True)  # the emergency account (models.GOD_USERNAME)
        self.user("gone", active=False)
        self.assertEqual(self.api("GET", "/users/", as_user="ana").status_code, 403)
        names = sorted(u["username"] for u in self.api("GET", "/users/", as_user="root").json())
        self.assertEqual(names, ["ana", "bea", "root"])

    def test_a_user_reads_their_own_account_but_not_another_one(self):
        own = self.api("GET", "/users/ana", as_user="ana")
        self.assertEqual((own.status_code, own.json()["username"], own.json()["email"]), (200, "ana", "ana@example.com"))
        self.assertNotIn("password", own.json())
        self.assertEqual(self.api("GET", "/users/bea", as_user="ana").status_code, 403)

    def test_an_admin_reads_anybody_and_gets_a_404_for_an_unknown_name(self):
        self.assertEqual(self.api("GET", "/users/bea", as_user="root").status_code, 200)
        missing = self.api("GET", "/users/nobody", as_user="root")
        self.assertEqual((missing.status_code, missing.json()["detail"]), (404, messages.USER_NOT_EXISTS))

    def test_every_route_of_the_router_needs_a_login(self):
        self.assertEqual(self.api("GET", "/users/ana").status_code, 401)
        self.assertEqual(self.api("GET", "/users/ana/library").status_code, 401)


class ProfileTests(UsersTestCase):
    def test_the_profile_of_a_season_adds_up_the_sessions_of_that_season(self):
        current = seasons.current()
        self.session(self.ana, "celeste", ago(hours=5), 60)
        self.session(self.ana, "hades", ago(hours=3), 30)
        self.session(self.ana, "celeste", datetime.datetime(current - 1, 5, 1, 20, 0), 120)
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        profile = self.api("GET", "/users/ana/profile", as_user="ana").json()
        self.assertEqual(profile["season"], current)
        self.assertEqual(profile["user"]["username"], "ana")
        self.assertEqual(profile["stats"]["played_time"], 90 * 60)
        self.assertEqual((profile["stats"]["played_games"], profile["stats"]["completed_games"]), (2, 1))
        self.assertEqual([g["game_id"] for g in profile["top_games"]], ["celeste", "hades"])
        self.assertIn(current - 1, profile["seasons"])

    def test_the_totals_and_other_seasons_can_be_asked_for(self):
        current = seasons.current()
        self.session(self.ana, "celeste", ago(hours=5), 60)
        self.session(self.ana, "celeste", datetime.datetime(current - 1, 5, 1, 20, 0), 120)
        everything = self.api("GET", "/users/ana/profile", as_user="ana", params={"season": "all"}).json()
        self.assertEqual((everything["season"], everything["stats"]["played_time"]), ("all", 180 * 60))
        last = self.api("GET", "/users/ana/profile", as_user="ana", params={"season": str(current - 1)}).json()
        self.assertEqual((last["season"], last["stats"]["played_time"]), (current - 1, 120 * 60))

    def test_the_season_must_be_a_year_or_all(self):
        for bad in ("abc", "20", "2026-1", "ALL"):
            self.assertEqual(self.api("GET", "/users/ana/profile", as_user="ana", params={"season": bad}).status_code, 422, bad)

    def test_the_streak_counts_consecutive_days(self):
        for days in (0, 1, 2):
            self.session(self.ana, "celeste", ago(days=days, hours=1), 30)
        stats = self.api("GET", "/users/ana/profile", as_user="ana").json()["stats"]
        self.assertEqual(stats["played_days"], 3)
        self.assertGreaterEqual(stats["best_streak"], stats["current_streak"])
        self.assertGreaterEqual(stats["current_streak"], 1)

    def test_the_latest_achievements_are_listed(self):
        achievement_id = self.scalar("SELECT id FROM achievements ORDER BY id LIMIT 1")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) VALUES (:u, :a, :d)"),
                         {"u": self.ana, "a": achievement_id, "d": TODAY()})
        profile = self.api("GET", "/users/ana/profile", as_user="ana").json()
        self.assertEqual(profile["stats"]["achievements"], 1)
        self.assertEqual(len(profile["achievements"]), 1)

    def test_a_profile_is_private(self):
        self.assertEqual(self.api("GET", "/users/ana/profile", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", "/users/ana/profile", as_user="root").status_code, 200)

    def test_an_empty_profile_is_all_zeros(self):
        stats = self.api("GET", "/users/bea/profile", as_user="bea").json()["stats"]
        self.assertEqual((stats["played_time"], stats["played_days"], stats["played_games"], stats["best_streak"]), (0, 0, 0, 0))


class UpdateProfileTests(UsersTestCase):
    def patch(self, as_user="ana", username="ana", **body):
        return self.api("PATCH", f"/users/{username}/profile", as_user=as_user, json=body)

    def test_it_changes_the_name_and_trims_it(self):
        response = self.patch(name="  Ana María  ")
        self.assertEqual((response.status_code, response.json()["name"]), (200, "Ana María"))
        self.assertEqual(self.scalar("SELECT name FROM users WHERE id = :i", i=self.ana), "Ana María")

    def test_an_empty_name_falls_back_to_the_nickname(self):
        self.assertEqual(self.patch(name="   ").json()["name"], "ana")

    def test_the_email_is_normalised_and_validated(self):
        self.assertEqual(self.patch(email="  New.Ana@Example.COM ").json()["email"], "new.ana@example.com")
        self.assertEqual(self.patch(email="not-an-email").json()["detail"], messages.EMAIL_INVALID)
        self.assertEqual(self.patch(email="   ").json()["detail"], messages.EMAIL_REQUIRED)
        self.assertEqual(self.patch(email=None).json()["detail"], messages.EMAIL_REQUIRED)

    def test_the_email_is_unique_in_any_case_but_may_be_kept(self):
        self.assertEqual(self.patch(email="BEA@example.com").json()["detail"], messages.EMAIL_IN_USE)
        self.assertEqual(self.patch(email="ana@example.com").status_code, 200)

    def test_the_telegram_id_is_unique(self):
        self.assertEqual(self.patch(as_user="bea", username="bea", telegram_id=111).json()["detail"], messages.TELEGRAM_ID_IN_USE)
        self.assertEqual(self.patch(as_user="bea", username="bea", telegram_id=222).status_code, 200)
        self.assertEqual(self.patch(telegram_id=111).status_code, 200)  # their own

    def test_it_only_changes_what_was_sent(self):
        self.patch(name="Only name")
        row = self.rows("SELECT email, telegram_id FROM users WHERE id = :i", i=self.ana)[0]
        self.assertEqual(tuple(row), ("ana@example.com", 111))

    def test_it_does_not_touch_the_privileges(self):
        self.patch(name="x", is_admin=True)
        self.assertEqual(self.scalar("SELECT is_admin FROM users WHERE id = :i", i=self.ana), 0)

    def test_only_the_owner_or_an_admin_edits_a_profile(self):
        self.assertEqual(self.patch(as_user="bea", name="hijack").status_code, 403)
        self.assertEqual(self.patch(as_user="root", name="By admin").status_code, 200)
        self.assertEqual(self.patch(as_user="root", username="nobody", name="x").status_code, 404)


class SettingsTests(UsersTestCase):
    def patch(self, as_user="ana", **body):
        return self.api("PATCH", "/users/ana/settings", as_user=as_user, json=body)

    def test_without_choices_every_value_is_the_default(self):
        body = self.api("GET", "/users/ana/settings", as_user="ana").json()
        self.assertEqual((body["forgotten_timer_hours"], body["timer_notice_minutes"]), (None, None))
        self.assertEqual(body["defaults"], {"forgotten_timer_hours": 4, "timer_notice_minutes": 10})

    def test_a_value_can_be_set_and_reset_with_null(self):
        self.assertEqual(self.patch(forgotten_timer_hours=6, timer_notice_minutes=30).json()["forgotten_timer_hours"], 6)
        self.assertEqual(self.api("GET", "/users/ana/settings", as_user="ana").json()["timer_notice_minutes"], 30)
        reset = self.patch(forgotten_timer_hours=None).json()
        self.assertEqual((reset["forgotten_timer_hours"], reset["timer_notice_minutes"]), (None, 30))

    def test_the_limits(self):
        for hours in (0, 25, -1):
            self.assertEqual(self.patch(forgotten_timer_hours=hours).status_code, 400, hours)
        for minutes in (9, 121, 0):
            self.assertEqual(self.patch(timer_notice_minutes=minutes).status_code, 400, minutes)
        for hours, minutes in ((1, 10), (24, 120)):
            self.assertEqual(self.patch(forgotten_timer_hours=hours, timer_notice_minutes=minutes).status_code, 200)

    def test_a_rejected_change_leaves_the_stored_values_alone(self):
        self.patch(forgotten_timer_hours=8)
        self.patch(forgotten_timer_hours=99)
        self.assertEqual(self.api("GET", "/users/ana/settings", as_user="ana").json()["forgotten_timer_hours"], 8)

    def test_settings_are_private_and_an_admin_may_read_them(self):
        self.assertEqual(self.api("GET", "/users/ana/settings", as_user="bea").status_code, 403)
        self.assertEqual(self.patch(as_user="bea", forgotten_timer_hours=3).status_code, 403)
        self.assertEqual(self.api("GET", "/users/ana/settings", as_user="root").status_code, 200)


class ChangePasswordTests(UsersTestCase):
    def change(self, current=PASSWORD, new=NEW_PASSWORD, as_user="ana", username="ana"):
        return self.api("POST", f"/users/{username}/password", as_user=as_user, json={"current_password": current, "new_password": new})

    def test_it_changes_the_password_and_ends_the_other_sessions(self):
        session = self.headers("ana")
        self.assertEqual(self.change().status_code, 200)
        self.assertEqual(self.api("POST", "/token", data={"username": "ana", "password": NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.api("POST", "/token", data={"username": "ana", "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.api("GET", "/auth/active_user", headers=session).status_code, 401)

    def test_the_current_password_must_be_right(self):
        response = self.change(current="not-the-password")
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.PASSWORD_WRONG))

    def test_the_new_password_must_follow_the_rules(self):
        for weak in ("short1!A", "alllowercase1234!", "NoSymbolsHere1234", "Has-No-Digits-Here!", "x" * 40 + "A1!"):
            response = self.change(new=weak)
            self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.PASSWORD_RULES), weak)

    def test_nobody_changes_another_person_s_password_not_even_an_admin(self):
        self.assertEqual(self.change(as_user="bea").status_code, 403)
        self.assertEqual(self.change(as_user="root").status_code, 403)
        self.assertEqual(self.api("POST", "/token", data={"username": "ana", "password": PASSWORD}).status_code, 200)


class LibraryTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        today = TODAY()
        self.celeste = self.library_entry(self.ana, "celeste", today, "pc")
        self.hades = self.library_entry(self.ana, "hades", today, "switch")
        self.old = self.library_entry(self.ana, "tetris", datetime.date(seasons.current() - 1, 4, 1), "pc")
        self.session(self.ana, "celeste", ago(hours=6), 60)
        self.session(self.ana, "hades", ago(hours=2), 30)

    def get(self, **params):
        return self.api("GET", "/users/ana/library", as_user="ana", params=params).json()

    def test_it_lists_every_season_most_recently_played_first(self):
        body = self.get()
        self.assertEqual((body["season"], body["total"]), (seasons.current(), 3))
        self.assertEqual([i["game_id"] for i in body["items"][:2]], ["hades", "celeste"])
        self.assertEqual(body["items"][-1]["game_id"], "tetris")

    def test_an_item_carries_what_the_page_needs(self):
        item = next(i for i in self.get()["items"] if i["game_id"] == "celeste")
        self.assertEqual((item["platform_id"], item["season"], item["played_time"], item["completed"]), ("pc", seasons.current(), 3600, False))
        self.assertEqual(item["game_name"], "Celeste")
        self.assertTrue(item["can_complete"])
        self.assertIsNone(item["complete_blocked"])

    def test_an_old_season_cannot_be_completed(self):
        old = next(i for i in self.get()["items"] if i["game_id"] == "tetris")
        self.assertFalse(old["can_complete"])
        self.assertEqual(old["complete_blocked"], "closed_season")

    def test_paging_and_the_filter_by_game(self):
        page = self.get(limit=1, offset=1)
        self.assertEqual((page["total"], [i["game_id"] for i in page["items"]]), (3, ["celeste"]))
        only = self.get(game_id="hades")
        self.assertEqual((only["total"], [i["game_id"] for i in only["items"]]), (1, ["hades"]))

    def test_the_bounds(self):
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            self.assertEqual(self.api("GET", "/users/ana/library", as_user="ana", params=params).status_code, 422, params)

    def test_a_library_is_private(self):
        self.assertEqual(self.api("GET", "/users/ana/library", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", "/users/ana/library", as_user="root").status_code, 200)


class RecommendationsTests(UsersTestCase):
    def test_it_suggests_what_others_play_and_the_user_never_had_most_shared_first(self):
        today = TODAY()
        self.library_entry(self.ana, "celeste", today)
        self.library_entry(self.bea, "celeste", today)
        for user in (self.bea, self.root):
            self.library_entry(user, "hades", today)
        self.library_entry(self.root, "tetris", today)
        body = self.api("GET", "/users/ana/recommendations", as_user="ana").json()
        ids = [r["game_id"] for r in body]
        self.assertEqual(ids, ["hades", "tetris"])  # celeste is already hers; hades is shared by two

    def test_the_limit_and_its_bounds(self):
        today = TODAY()
        for game_id in ("celeste", "hades", "tetris"):
            self.library_entry(self.bea, game_id, today)
        self.assertEqual(len(self.api("GET", "/users/ana/recommendations", as_user="ana", params={"limit": 2}).json()), 2)
        for limit in (0, 51):
            self.assertEqual(self.api("GET", "/users/ana/recommendations", as_user="ana", params={"limit": limit}).status_code, 422)

    def test_it_is_private(self):
        self.assertEqual(self.api("GET", "/users/ana/recommendations", as_user="bea").status_code, 403)


class CompletionTests(UsersTestCase):
    def setUp(self):
        super().setUp()
        self.entry = self.library_entry(self.ana, "celeste", TODAY() - timedelta(days=5), "pc")

    def complete(self, entry=None, as_user="ana", username="ana", **body):
        params = {"silent": body.pop("silent")} if "silent" in body else {}
        body.setdefault("completed", True)
        return self.api("PATCH", f"/users/{username}/library/{entry or self.entry}/completion", as_user=as_user, params=params, json=body)

    def test_it_completes_a_pending_entry_today_and_schedules_the_announcement(self):
        response = self.complete()
        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertTrue(item["completed"])
        self.assertEqual(item["completed_date"], TODAY().isoformat())
        self.background["after_completion"].assert_called_once_with(self.entry, False)

    def test_silent_completions_are_not_announced_to_the_group(self):
        self.complete(silent=True)
        self.background["after_completion"].assert_called_once_with(self.entry, True)

    def test_it_can_be_completed_on_an_earlier_day_of_the_season(self):
        day = TODAY() - timedelta(days=2)
        self.assertEqual(self.complete(completed_date=day.isoformat()).json()["completed_date"], day.isoformat())

    def test_the_date_rules(self):
        started = TODAY() - timedelta(days=5)
        cases = {
            "future": (TODAY() + timedelta(days=1)),
            "before the start": started - timedelta(days=1),
            "another season": datetime.date(seasons.current() - 1, 6, 1),
        }
        for name, date in cases.items():
            with self.subTest(name):
                self.assertEqual(self.complete(completed_date=date.isoformat()).status_code, 400)
        self.background["after_completion"].assert_not_called()

    def test_a_game_is_completed_once_per_season_even_on_another_platform(self):
        other_platform = self.library_entry(self.ana, "celeste", TODAY(), "switch")
        self.assertEqual(self.complete().status_code, 200)
        second = self.complete(entry=other_platform)
        self.assertEqual((second.status_code, second.json()["detail"]), (409, messages.ALREADY_COMPLETED_IN_SEASON))
        blocked = next(i for i in self.api("GET", "/users/ana/library", as_user="ana").json()["items"] if i["id"] == other_platform)
        self.assertEqual(blocked["complete_blocked"], "completed_in_season")

    def test_a_closed_season_cannot_be_completed(self):
        old = self.library_entry(self.ana, "hades", datetime.date(seasons.current() - 1, 4, 1), "pc")
        response = self.complete(entry=old)
        self.assertEqual((response.status_code, response.json()["detail"]), (409, messages.COMPLETE_ONLY_CURRENT_SEASON))

    def test_the_date_of_a_completed_entry_can_change_but_not_without_saying_which(self):
        self.complete()
        day = TODAY() - timedelta(days=3)
        self.assertEqual(self.complete(completed_date=day.isoformat()).json()["completed_date"], day.isoformat())
        again = self.complete()
        self.assertEqual((again.status_code, again.json()["detail"]), (409, messages.GAME_ALREADY_COMPLETED))
        self.assertEqual(self.complete(completed_date=(TODAY() + timedelta(days=1)).isoformat()).status_code, 400)

    def test_a_completion_can_be_undone_and_the_entry_stays(self):
        self.complete()
        item = self.complete(completed=False).json()
        self.assertEqual((item["completed"], item["completed_date"]), (False, None))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE id = :i", i=self.entry), 1)
        self.assertEqual(self.complete(completed=False).status_code, 200)  # undoing a pending one is harmless

    def test_after_undoing_it_can_be_completed_again(self):
        self.complete()
        self.complete(completed=False)
        self.assertEqual(self.complete().status_code, 200)

    def test_unknown_entries_and_entries_of_somebody_else(self):
        self.assertEqual(self.complete(entry=999999).status_code, 404)
        theirs = self.library_entry(self.bea, "hades", TODAY(), "pc")
        self.assertEqual(self.complete(entry=theirs).status_code, 404)

    def test_only_the_owner_or_an_admin_completes(self):
        self.assertEqual(self.complete(as_user="bea").status_code, 403)
        self.assertEqual(self.complete(as_user="root").status_code, 200)


class AvatarTests(UsersTestCase):
    def upload(self, data, name="a.png", as_user="ana", username="ana"):
        return self.api("PATCH", f"/users/{username}/avatar", as_user=as_user, files={"file": (name, data, "image/png")})

    def test_a_picture_is_stored_and_served_back(self):
        image = png()
        self.assertEqual(self.upload(image).status_code, 200)
        served = self.api("GET", "/users/ana/avatar", as_user="ana")
        self.assertEqual((served.status_code, served.headers["content-type"], served.content), (200, "image/png", image))

    def test_there_is_a_404_until_one_is_uploaded(self):
        self.assertEqual(self.api("GET", "/users/ana/avatar", as_user="ana").status_code, 404)

    def test_only_png_and_jpeg_are_accepted_whatever_the_name_says(self):
        response = self.upload(gif(), name="looks-like.png")
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.FILE_TYPE_NOT_ALLOWED))
        self.assertEqual(self.upload(b"not an image at all").status_code, 400)
        self.assertEqual(self.upload(b"").status_code, 400)

    def test_the_size_is_limited(self):
        response = self.upload(b"\x89PNG" + b"0" * (2 * 1024 * 1024 + 10))
        self.assertEqual((response.status_code, response.json()["detail"]), (400, messages.FILE_TOO_BIG))

    def test_a_new_picture_replaces_the_old_one(self):
        self.upload(png())
        jpeg = io.BytesIO()
        Image.new("RGB", (4, 4), (0, 0, 255)).save(jpeg, "JPEG")
        self.upload(jpeg.getvalue(), name="b.jpg")
        served = self.api("GET", "/users/ana/avatar", as_user="ana")
        self.assertEqual((served.headers["content-type"], served.content), ("image/jpeg", jpeg.getvalue()))

    def test_avatars_are_private_to_the_owner_and_the_admins(self):
        self.assertEqual(self.upload(png(), as_user="bea").status_code, 403)
        self.upload(png())
        self.assertEqual(self.api("GET", "/users/ana/avatar", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", "/users/ana/avatar", as_user="root").status_code, 200)
        self.assertEqual(self.upload(png(), as_user="root", username="nobody").status_code, 404)
