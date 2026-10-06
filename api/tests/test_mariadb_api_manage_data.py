"""The admin panel's data routes (users, games, sessions, library, platforms, achievements) through real
requests (MariaDB required, see api_support.py). The operations side of the panel is in
test_mariadb_api_manage_ops.py."""
import datetime
from datetime import timedelta

from sqlalchemy import text

from src.utils import seasons
from tests.api_support import PASSWORD, ApiTestCase

NEW_PASSWORD = "An0ther-secret!pw"


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


class ManageTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana", telegram_id=111)
        self.bea = self.user("bea")
        self.root = self.user("root", admin=True)
        self.celeste = self.game("celeste", "Celeste", rawg_id=101)
        self.hades = self.game("hades", "Hades")

    def admin(self, method, path, **kwargs):
        return self.api(method, f"/manage{path}", as_user="root", **kwargs)


class UsersAdminTests(ManageTestCase):
    def new_user(self, **overrides):
        body = {"email": "New@Example.com", "username": " newbie ", "password": PASSWORD, "name": " New Bie ", **overrides}
        return self.admin("POST", "/users", json=body)

    def test_the_list_counts_sessions_and_library_and_pages(self):
        self.session(self.ana, "celeste", ago(hours=5), 30)
        self.session(self.ana, "hades", ago(hours=3), 30)
        self.library_entry(self.ana, "celeste", datetime.date.today())
        body = self.admin("GET", "/users").json()
        self.assertEqual(body["total"], 3)
        by_name = {u["username"]: u for u in body["items"]}
        self.assertEqual((by_name["ana"]["sessions"], by_name["ana"]["library"], by_name["bea"]["sessions"]), (2, 1, 0))
        self.assertEqual([u["username"] for u in body["items"]], ["ana", "bea", "root"])  # by username
        self.assertEqual([u["username"] for u in self.admin("GET", "/users", params={"limit": 1, "offset": 1}).json()["items"]], ["bea"])

    def test_the_list_searches_username_name_and_email_and_escapes_wildcards(self):
        self.assertEqual([u["username"] for u in self.admin("GET", "/users", params={"search": "be"}).json()["items"]], ["bea"])
        self.assertEqual([u["username"] for u in self.admin("GET", "/users", params={"search": "ANA@"}).json()["items"]], ["ana"])
        self.assertEqual(self.admin("GET", "/users", params={"search": "%"}).json()["total"], 0)  # a literal percent sign
        self.assertEqual(self.admin("GET", "/users", params={"search": "_"}).json()["total"], 0)

    def test_the_list_bounds(self):
        for params in ({"limit": 0}, {"limit": 201}, {"offset": -1}):
            self.assertEqual(self.admin("GET", "/users", params=params).status_code, 422)

    def test_it_creates_an_account_that_can_log_in(self):
        response = self.new_user(telegram_id=555)
        self.assertEqual(response.status_code, 201)
        user = response.json()
        self.assertEqual((user["username"], user["email"], user["name"], user["telegram_id"]), ("newbie", "new@example.com", "New Bie", 555))
        self.assertEqual((user["is_admin"], user["is_active"]), (False, True))
        self.assertNotIn("password", user)
        self.assertEqual(self.api("POST", "/token", data={"username": "newbie", "password": PASSWORD}).status_code, 200)

    def test_it_can_create_an_admin_or_a_disabled_account(self):
        user = self.new_user(is_admin=True, is_active=False).json()
        self.assertEqual((user["is_admin"], user["is_active"]), (True, False))

    def test_the_rules_for_a_new_account(self):
        cases = {
            "no email": ({"email": "  "}, 400),
            "bad email": ({"email": "not-an-email"}, 400),
            "email taken": ({"email": "ANA@example.com"}, 409),
            "empty username": ({"username": "   "}, 400),
            "at sign in the username": ({"username": "a@b"}, 400),
            "space in the username": ({"username": "a b"}, 400),
            "username taken": ({"username": "ana"}, 409),
            "telegram id taken": ({"telegram_id": 111}, 409),
            "weak password": ({"password": "weak"}, 400),
        }
        for name, (overrides, status) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.new_user(**overrides).status_code, status)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users"), 3)

    def test_patching_changes_only_what_is_sent(self):
        response = self.admin("PATCH", f"/users/{self.bea}", json={"name": "  Beatriz  ", "telegram_id": 999})
        user = response.json()
        self.assertEqual((user["name"], user["telegram_id"], user["username"]), ("Beatriz", 999, "bea"))

    def test_an_empty_name_falls_back_to_the_nickname(self):
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"name": " "}).json()["name"], "bea")

    def test_patching_the_login_fields_is_checked_like_creating(self):
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"email": "ANA@example.com"}).status_code, 409)
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"email": "nope"}).status_code, 400)
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"username": "ana"}).status_code, 409)
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"username": "with space"}).status_code, 400)
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"telegram_id": 111}).status_code, 409)
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"username": " beatriz ", "email": "Bea.New@Example.com"}).json()["username"], "beatriz")
        self.assertEqual(self.admin("PATCH", f"/users/{self.bea}", json={"email": "bea.new@example.com"}).status_code, 200)  # their own

    def test_an_admin_can_promote_and_disable_others_but_not_demote_or_disable_themselves(self):
        promoted = self.admin("PATCH", f"/users/{self.bea}", json={"is_admin": True, "is_active": False}).json()
        self.assertEqual((promoted["is_admin"], promoted["is_active"]), (True, False))
        self.assertEqual(self.admin("PATCH", f"/users/{self.root}", json={"is_admin": False}).status_code, 400)
        self.assertEqual(self.admin("PATCH", f"/users/{self.root}", json={"is_active": False}).status_code, 400)
        self.assertEqual(self.admin("PATCH", f"/users/{self.root}", json={"name": "Boss"}).status_code, 200)

    def test_a_disabled_account_can_no_longer_log_in(self):
        self.admin("PATCH", f"/users/{self.bea}", json={"is_active": False})
        self.assertEqual(self.api("POST", "/token", data={"username": "bea", "password": PASSWORD}).status_code, 403)

    def test_unknown_users_are_404(self):
        self.assertEqual(self.admin("PATCH", "/users/9999", json={"name": "x"}).status_code, 404)
        self.assertEqual(self.admin("POST", "/users/9999/password", json={"password": NEW_PASSWORD}).status_code, 404)
        self.assertEqual(self.admin("DELETE", "/users/9999").status_code, 404)

    def test_setting_a_password_enforces_the_rules_and_signs_the_user_out(self):
        session = self.headers("bea")
        self.assertEqual(self.admin("POST", f"/users/{self.bea}/password", json={"password": "weak"}).status_code, 400)
        self.assertEqual(self.admin("POST", f"/users/{self.bea}/password", json={"password": NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.api("POST", "/token", data={"username": "bea", "password": NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.api("GET", "/auth/active_user", headers=session).status_code, 401)

    def test_deleting_an_account_with_data_needs_confirmation_and_lists_what_goes(self):
        self.session(self.ana, "celeste", ago(hours=4), 30)
        self.library_entry(self.ana, "celeste", datetime.date.today())
        refused = self.admin("DELETE", f"/users/{self.ana}")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"]["counts"], {"sesiones": 1, "biblioteca": 1})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE id = :i", i=self.ana), 1)

    def test_forcing_the_deletion_removes_the_account_and_everything_that_hangs_from_it(self):
        self.session(self.ana, "celeste", ago(hours=4), 30)
        self.library_entry(self.ana, "celeste", datetime.date.today())
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, 'https://p/x', 'k', 'a')"), {"u": self.ana})
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) SELECT :u, id, CURDATE() FROM achievements LIMIT 1"), {"u": self.ana})
        self.assertEqual(self.admin("DELETE", f"/users/{self.ana}", params={"force": True}).status_code, 200)
        for table in ("users_games", "game_timers", "users_achievements", "push_subscriptions"):
            self.assertEqual(self.scalar(f"SELECT COUNT(*) FROM {table} WHERE user_id = :u", u=self.ana), 0, table)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users WHERE id = :i", i=self.ana), 0)

    def test_an_account_without_data_is_deleted_straight_away_and_never_your_own(self):
        self.assertEqual(self.admin("DELETE", f"/users/{self.bea}").status_code, 200)
        self.assertEqual(self.admin("DELETE", f"/users/{self.root}", params={"force": True}).status_code, 400)


class GamesAdminTests(ManageTestCase):
    def setUp(self):
        super().setUp()
        self.game("tetris", "Tetris", rawg_id=303, release_date=datetime.date(1984, 6, 6))
        self.session(self.ana, "celeste", ago(hours=6), 30)
        self.session(self.ana, "celeste", ago(hours=4), 30)
        self.session(self.bea, "celeste", ago(hours=2), 30)
        self.library_entry(self.ana, "celeste", datetime.date.today())
        self.library_entry(self.bea, "celeste", datetime.date.today())
        self.library_entry(self.bea, "hades", datetime.date.today())

    def games(self, **params):
        return self.admin("GET", "/games", params=params).json()

    def test_each_game_comes_with_its_usage(self):
        by_id = {g["id"]: g for g in self.games()["items"]}
        self.assertEqual((by_id["celeste"]["sessions"], by_id["celeste"]["players"]), (3, 2))
        self.assertEqual((by_id["hades"]["sessions"], by_id["hades"]["players"]), (0, 1))
        self.assertEqual((by_id["tetris"]["sessions"], by_id["tetris"]["players"]), (0, 0))
        self.assertEqual(self.games()["total"], 3)

    def test_filters(self):
        self.assertEqual([g["id"] for g in self.games(rawg="unlinked")["items"]], ["hades"])
        self.assertEqual(sorted(g["id"] for g in self.games(rawg="linked")["items"]), ["celeste", "tetris"])
        self.assertEqual(sorted(g["id"] for g in self.games(usage="used")["items"]), ["celeste", "hades"])
        self.assertEqual([g["id"] for g in self.games(usage="unused")["items"]], ["tetris"])
        self.assertEqual([g["id"] for g in self.games(search="tet")["items"]], ["tetris"])
        self.assertEqual(self.games(search="%")["total"], 0)

    def test_sorting_and_paging(self):
        self.assertEqual([g["id"] for g in self.games(sort="sessions", order="desc")["items"]][0], "celeste")
        self.assertEqual([g["id"] for g in self.games(sort="release_date")["items"]][-1], "tetris")  # NULLs first when ascending
        self.assertEqual([g["id"] for g in self.games(limit=1, offset=2)["items"]], ["tetris"])

    def test_invalid_filters_are_rejected(self):
        for params in ({"rawg": "maybe"}, {"usage": "x"}, {"sort": "dev"}, {"order": "up"}, {"limit": 0}, {"limit": 201}):
            self.assertEqual(self.admin("GET", "/games", params=params).status_code, 422, params)

    def test_patching_a_game(self):
        done = self.admin("PATCH", "/games/hades", json={"dev": "Supergiant", "avg_time": 22, "release_date": "2020-09-17", "rawg_id": 404}).json()
        self.assertEqual((done["dev"], done["avg_time"], done["release_date"], done["rawg_id"]), ("Supergiant", 22, "2020-09-17", 404))
        self.assertEqual(self.admin("PATCH", "/games/hades", json={"name": "  "}).status_code, 400)
        self.assertEqual(self.admin("PATCH", "/games/hades", json={"name": "Celeste"}).status_code, 409)  # names are unique
        self.assertEqual(self.admin("PATCH", "/games/nope", json={"dev": "x"}).status_code, 404)

    def test_deleting_a_game_in_use_lists_what_goes_and_needs_confirmation(self):
        refused = self.admin("DELETE", "/games/celeste")
        self.assertEqual((refused.status_code, refused.json()["detail"]["counts"]), (409, {"sesiones": 3, "biblioteca": 2}))
        self.assertEqual(self.admin("DELETE", "/games/celeste", params={"force": True}).status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers WHERE game_id = 'celeste'"), 0)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE game_id = 'celeste'"), 0)

    def test_an_unused_game_goes_without_asking_and_an_unknown_one_is_404(self):
        self.assertEqual(self.admin("DELETE", "/games/tetris").status_code, 200)
        self.assertEqual(self.admin("DELETE", "/games/tetris").status_code, 404)


class SessionsAdminTests(ManageTestCase):
    def body(self, **overrides):
        start = ago(hours=5)
        return {"user_id": self.ana, "game_id": "celeste", "platform": "pc", "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=1)).isoformat(), **overrides}

    def test_an_admin_records_a_finished_session_for_anybody(self):
        response = self.admin("POST", "/timers", json=self.body(notes="forgot to stop"))
        self.assertEqual(response.status_code, 201)
        timer = response.json()
        self.assertEqual((timer["user_id"], timer["duration_seconds"], timer["is_active"], timer["notes"]), (self.ana, 3600, False, "forgot to stop"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u AND game_id = 'celeste'", u=self.ana), 1)

    def test_the_rules_for_a_recorded_session(self):
        end_before = self.body(end_time=ago(hours=6).isoformat())
        self.assertEqual(self.admin("POST", "/timers", json=end_before).status_code, 400)
        self.assertEqual(self.admin("POST", "/timers", json=self.body(user_id=9999)).status_code, 404)
        self.assertEqual(self.admin("POST", "/timers", json=self.body(game_id="nope")).status_code, 404)
        self.assertEqual(self.admin("POST", "/timers", json=self.body(notes="x" * 501)).status_code, 422)

    def test_the_same_session_twice_is_a_conflict(self):
        self.assertEqual(self.admin("POST", "/timers", json=self.body()).status_code, 201)
        self.assertEqual(self.admin("POST", "/timers", json=self.body()).status_code, 409)

    def listing(self):
        self.session(self.ana, "celeste", ago(hours=9), 60, "pc")
        self.session(self.ana, "hades", ago(hours=7), 30, "switch")
        self.session(self.bea, "celeste", ago(hours=5), 90, "pc")
        self.api("POST", "/timers/start", as_user="bea", json={"user_id": self.bea, "game_id": "hades", "platform": "switch"})

    def test_the_list_filters(self):
        self.listing()
        def ids(**params):
            return [(t["user"], t["game"]) for t in self.admin("GET", "/timers", params=params).json()["items"]]
        self.assertEqual(self.admin("GET", "/timers").json()["total"], 4)
        self.assertEqual(sorted(ids(user_id=self.ana)), [("ana", "Celeste"), ("ana", "Hades")])
        self.assertEqual(sorted(ids(game_id="celeste")), [("ana", "Celeste"), ("bea", "Celeste")])
        self.assertEqual(ids(active=True), [("bea", "Hades")])
        self.assertEqual(len(ids(active=False)), 3)
        self.assertEqual(sorted(ids(platform="switch")), [("ana", "Hades"), ("bea", "Hades")])
        self.assertEqual(len(ids(season=seasons.current())), 4)
        self.assertEqual(ids(season=1999), [])

    def test_the_list_sorts_and_pages(self):
        self.listing()
        newest_first = self.admin("GET", "/timers").json()["items"]
        self.assertTrue(newest_first[0]["is_active"])  # the running one started last
        by_duration = self.admin("GET", "/timers", params={"sort": "duration", "order": "asc"}).json()["items"]
        durations = [t["duration_seconds"] for t in by_duration if t["duration_seconds"] is not None]
        self.assertEqual(durations, sorted(durations))
        self.assertEqual(len(self.admin("GET", "/timers", params={"limit": 2, "offset": 3}).json()["items"]), 1)
        self.assertEqual(self.admin("GET", "/timers", params={"sort": "dev"}).status_code, 422)

    def test_editing_changes_the_times_and_recomputes_the_duration(self):
        body = self.body()
        timer_id = self.admin("POST", "/timers", json=body).json()["id"]
        # Derived from the start, not from a second reading of the clock: two readings can straddle a second
        end = datetime.datetime.fromisoformat(body["start_time"]) + timedelta(hours=2)
        done = self.admin("PATCH", f"/timers/{timer_id}", json={"end_time": end.isoformat(), "platform": "switch", "notes": "fixed"}).json()
        self.assertEqual((done["duration_seconds"], done["platform"], done["notes"]), (2 * 3600, "switch", "fixed"))
        self.assertEqual(self.admin("PATCH", f"/timers/{timer_id}", json={"end_time": ago(hours=6).isoformat()}).status_code, 400)
        self.assertEqual(self.admin("PATCH", "/timers/99999", json={"notes": "x"}).status_code, 404)

    def test_setting_an_end_time_finishes_a_stuck_timer(self):
        self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "celeste", "platform": "pc"})
        timer_id = self.scalar("SELECT id FROM game_timers")
        start = self.scalar("SELECT start_time FROM game_timers WHERE id = :i", i=timer_id)
        done = self.admin("PATCH", f"/timers/{timer_id}", json={"end_time": (start + timedelta(minutes=45)).isoformat()}).json()
        self.assertEqual((done["is_active"], done["duration_seconds"]), (False, 45 * 60))
        # the follow-up of a stopped timer is scheduled so that its notification is cleared
        self.background["after_timer_stop"].assert_called_once_with(self.ana, "celeste", 45 * 60)

    def test_deleting_a_running_timer_clears_its_notification(self):
        self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "celeste", "platform": "pc"})
        timer_id = self.scalar("SELECT id FROM game_timers")
        self.assertEqual(self.admin("DELETE", f"/timers/{timer_id}").status_code, 200)
        self.background["after_timer_stop"].assert_called_once_with(self.ana, "celeste", None)
        self.assertEqual(self.admin("DELETE", f"/timers/{timer_id}").status_code, 404)

    def test_every_change_of_an_admin_checks_the_achievements_of_that_player_silently(self):
        check = self.background["after_session_change"]
        created = self.admin("POST", "/timers", json=self.body()).json()
        timer_id, season = created["id"], seasons.of(datetime.datetime.fromisoformat(created["start_time"]))
        check.assert_called_once_with(self.ana, True, recalculate=[season])
        check.reset_mock()
        self.admin("PATCH", f"/timers/{timer_id}", json={"notes": "fixed"})
        check.assert_called_once_with(self.ana, True, recalculate=[season])
        check.reset_mock()
        self.admin("DELETE", f"/timers/{timer_id}")
        check.assert_called_once_with(self.ana, True, recalculate=[season])

    def test_moving_a_session_to_another_season_works_out_both_again(self):
        check = self.background["after_session_change"]
        created = self.admin("POST", "/timers", json=self.body()).json()
        check.reset_mock()
        start = datetime.datetime.fromisoformat(created["start_time"])
        last_year = start.replace(year=start.year - 1)
        self.admin("PATCH", f"/timers/{created['id']}", json={"start_time": last_year.isoformat(), "end_time": (last_year + timedelta(hours=1)).isoformat()})
        check.assert_called_once_with(self.ana, True, recalculate=[start.year - 1, start.year])

    def test_a_rejected_change_checks_nothing(self):
        self.admin("POST", "/timers", json=self.body(end_time=ago(hours=6).isoformat()))
        self.background["after_session_change"].assert_not_called()

    def test_deleting_a_finished_session_schedules_nothing(self):
        timer_id = self.session(self.ana, "celeste", ago(hours=4), 30)
        self.admin("DELETE", f"/timers/{timer_id}")
        self.background["after_timer_stop"].assert_not_called()


class LibraryAdminTests(ManageTestCase):
    def setUp(self):
        super().setUp()
        today = datetime.date.today()
        self.first = self.library_entry(self.ana, "celeste", today, "pc", completed=1, completed_date=today)
        self.second = self.library_entry(self.bea, "hades", today, "switch")
        self.old = self.library_entry(self.ana, "hades", datetime.date(seasons.current() - 1, 3, 1), "pc")

    def entries(self, **params):
        return self.admin("GET", "/library", params=params).json()

    def test_the_list_filters_sorts_and_pages(self):
        self.assertEqual(self.entries()["total"], 3)
        self.assertEqual(sorted(i["game"] for i in self.entries(user_id=self.ana)["items"]), ["Celeste", "Hades"])
        self.assertEqual([i["id"] for i in self.entries(completed="yes")["items"]], [self.first])
        self.assertEqual(sorted(i["id"] for i in self.entries(completed="no")["items"]), sorted([self.second, self.old]))
        self.assertEqual([i["id"] for i in self.entries(season=seasons.current() - 1)["items"]], [self.old])
        self.assertEqual(sorted(i["id"] for i in self.entries(platform="switch")["items"]), [self.second])
        self.assertEqual([i["season"] for i in self.entries(sort="season", order="asc")["items"]][0], seasons.current() - 1)
        self.assertEqual(len(self.entries(limit=1, offset=2)["items"]), 1)
        for params in ({"completed": "maybe"}, {"sort": "x"}, {"limit": 0}):
            self.assertEqual(self.admin("GET", "/library", params=params).status_code, 422)

    def test_an_entry_is_created_for_a_user_and_a_game_with_the_season_of_its_date(self):
        response = self.admin("POST", "/library", json={"user_id": self.bea, "game_id": "celeste", "platform": "pc", "started_date": "2024-05-05"})
        self.assertEqual(response.status_code, 201)
        entry = response.json()
        self.assertEqual((entry["season"], entry["completed"], entry["started_date"]), (2024, False, "2024-05-05"))
        self.assertEqual(self.admin("POST", "/library", json={"user_id": self.bea, "game_id": "celeste"}).json()["season"], seasons.current())

    def test_an_entry_is_unique_per_user_game_platform_and_season(self):
        body = {"user_id": self.ana, "game_id": "celeste", "platform": "pc"}
        self.assertEqual(self.admin("POST", "/library", json=body).status_code, 409)
        self.assertEqual(self.admin("POST", "/library", json={**body, "platform": "switch"}).status_code, 201)
        self.assertEqual(self.admin("POST", "/library", json={**body, "user_id": 9999}).status_code, 404)
        self.assertEqual(self.admin("POST", "/library", json={**body, "game_id": "nope"}).status_code, 404)

    def test_editing_an_entry(self):
        done = self.admin("PATCH", f"/library/{self.second}", json={"completed": True, "completed_date": "2026-01-02"}).json()
        self.assertEqual((done["completed"], done["completed_date"]), (True, "2026-01-02"))
        self.assertFalse(self.admin("PATCH", f"/library/{self.second}", json={"completed": False}).json()["completed"])
        self.assertEqual(self.admin("PATCH", "/library/9999", json={"completed": True}).status_code, 404)

    def test_deleting_an_entry(self):
        self.assertEqual(self.admin("DELETE", f"/library/{self.second}").status_code, 200)
        self.assertEqual(self.admin("DELETE", f"/library/{self.second}").status_code, 404)
        self.assertEqual(self.entries()["total"], 2)

    def test_every_change_of_an_admin_checks_the_achievements_of_that_player_silently(self):
        check = self.background["after_session_change"]
        season = seasons.current()
        created = self.admin("POST", "/library", json={"user_id": self.bea, "game_id": "celeste", "platform": "pc"}).json()
        check.assert_called_once_with(self.bea, True, recalculate=[season])
        check.reset_mock()
        self.admin("PATCH", f"/library/{created['id']}", json={"completed": True})
        check.assert_called_once_with(self.bea, True, recalculate=[season])
        check.reset_mock()
        self.admin("PATCH", f"/library/{created['id']}", json={"started_date": f"{season - 1}-06-01"})
        check.assert_called_once_with(self.bea, True, recalculate=[season - 1, season])  # it changed season
        check.reset_mock()
        self.admin("DELETE", f"/library/{created['id']}")
        check.assert_called_once_with(self.bea, True, recalculate=[season - 1])


class ScoresAdminTests(ManageTestCase):
    def setUp(self):
        super().setUp()
        today = datetime.date.today()
        self.library_entry(self.ana, "celeste", today, "pc")
        self.library_entry(self.bea, "hades", today, "switch")

    def scores(self, **params):
        return self.admin("GET", "/scores", params=params).json()

    def create(self, user, game, score):
        return self.admin("POST", "/scores", json={"user_id": user, "game_id": game, "score": score})

    def test_a_score_is_created_listed_filtered_and_sorted(self):
        first = self.create(self.ana, "celeste", 90)
        self.assertEqual(first.status_code, 201)
        self.assertEqual((first.json()["score"], first.json()["game_id"]), (90, "celeste"))
        self.create(self.bea, "hades", 40)
        body = self.scores(sort="score", order="asc")
        self.assertEqual((body["total"], [i["score"] for i in body["items"]], [i["user"] for i in body["items"]]), (2, [40, 90], ["bea", "ana"]))
        self.assertEqual([i["game"] for i in self.scores(user_id=self.ana)["items"]], ["Celeste"])
        self.assertEqual([i["user"] for i in self.scores(game_id="hades")["items"]], ["bea"])
        self.assertEqual(self.admin("GET", "/scores", params={"sort": "x"}).status_code, 422)

    def test_a_user_rates_a_game_once(self):
        self.create(self.ana, "celeste", 90)
        self.assertEqual(self.create(self.ana, "celeste", 10).status_code, 409)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_scores"), 1)

    def test_the_rules_of_a_score(self):
        for score in (0, 101, -3):
            self.assertEqual(self.create(self.ana, "celeste", score).status_code, 422, score)
        self.assertEqual(self.admin("POST", "/scores", json={"user_id": self.ana, "game_id": "celeste", "score": 7.5}).status_code, 422)
        self.assertEqual(self.create(9999, "celeste", 50).status_code, 404)
        self.assertEqual(self.create(self.ana, "nope", 50).status_code, 404)

    def test_it_is_edited_and_deleted(self):
        row = self.create(self.ana, "celeste", 90).json()["id"]
        self.assertEqual(self.admin("PATCH", f"/scores/{row}", json={"score": 55}).json()["score"], 55)
        self.assertEqual(self.admin("PATCH", f"/scores/{row}", json={"score": 101}).status_code, 422)
        self.assertEqual(self.admin("PATCH", "/scores/9999", json={"score": 5}).status_code, 404)
        self.assertEqual(self.admin("DELETE", f"/scores/{row}").status_code, 200)
        self.assertEqual(self.admin("DELETE", f"/scores/{row}").status_code, 404)

    def test_deleting_a_user_or_a_game_takes_its_scores_after_the_confirmation(self):
        self.create(self.ana, "celeste", 90)
        refused = self.admin("DELETE", f"/games/celeste")
        self.assertEqual(refused.status_code, 409)
        self.assertEqual(refused.json()["detail"]["counts"]["puntuaciones"], 1)
        self.assertEqual(self.admin("DELETE", "/games/celeste", params={"force": True}).status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_scores"), 0)
        self.create(self.bea, "hades", 40)
        self.assertEqual(self.admin("DELETE", f"/users/{self.bea}", params={"force": True}).status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_scores"), 0)


class PlatformsAdminTests(ManageTestCase):
    def test_the_list_counts_how_much_each_platform_is_used(self):
        self.session(self.ana, "celeste", ago(hours=4), 30, "pc")
        self.library_entry(self.ana, "celeste", datetime.date.today(), "pc")
        by_id = {p["id"]: p for p in self.admin("GET", "/platforms").json()}
        self.assertEqual((by_id["pc"]["sessions"], by_id["pc"]["library"], by_id["switch"]["sessions"]), (1, 1, 0))
        names = [p["name"] for p in self.admin("GET", "/platforms").json()]
        self.assertEqual(names, sorted(names))

    def test_a_new_platform_gets_a_readable_id_that_never_collides(self):
        first = self.admin("POST", "/platforms", json={"name": "  Atari Lynx  "})
        self.assertEqual((first.status_code, first.json()["id"], first.json()["name"]), (201, "atari-lynx", "Atari Lynx"))
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "Atari  Lynx!"}).json()["id"], "atari-lynx-2")
        accented = self.admin("POST", "/platforms", json={"name": "Máquina Árcade"}).json()
        self.assertEqual(accented["id"], "maquina-arcade")
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "!!!"}).json()["id"], "platform")
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "???"}).json()["id"], "platform-2")

    def test_names_are_validated_and_unique_ignoring_case(self):
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "   "}).status_code, 400)
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "x" * 101}).status_code, 400)
        self.assertEqual(self.admin("POST", "/platforms", json={"name": "nintendo switch"}).status_code, 409)

    def test_renaming_keeps_the_id_and_what_points_at_it(self):
        self.session(self.ana, "celeste", ago(hours=4), 30, "switch")
        done = self.admin("PATCH", "/platforms/switch", json={"name": "Switch OLED"}).json()
        self.assertEqual((done["id"], done["name"], done["sessions"] if "sessions" in done else 0), ("switch", "Switch OLED", 0))
        self.assertEqual(self.scalar("SELECT platform FROM game_timers"), "switch")
        self.assertEqual(self.admin("PATCH", "/platforms/switch", json={"name": "PC"}).status_code, 409)
        self.assertEqual(self.admin("PATCH", "/platforms/switch", json={"name": "Switch OLED"}).status_code, 200)  # its own name
        self.assertEqual(self.admin("PATCH", "/platforms/nope", json={"name": "x"}).status_code, 404)

    def test_a_platform_in_use_cannot_be_deleted_one_nobody_uses_can(self):
        self.session(self.ana, "celeste", ago(hours=4), 30, "pc")
        refused = self.admin("DELETE", "/platforms/pc")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("1 sesiones", refused.json()["detail"])
        created = self.admin("POST", "/platforms", json={"name": "Temporary"}).json()["id"]
        self.assertEqual(self.admin("DELETE", f"/platforms/{created}").status_code, 200)
        self.assertEqual(self.admin("DELETE", f"/platforms/{created}").status_code, 404)


class AchievementsAdminTests(ManageTestCase):
    def award(self, user_id, achievement_id, date, game_id=None):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date, game_id) VALUES (:u, :a, :d, :g)"),
                         {"u": user_id, "a": achievement_id, "d": date, "g": game_id})
            return conn.execute(text("SELECT MAX(id) FROM users_achievements")).scalar()

    def ids(self):
        return [r[0] for r in self.rows("SELECT id FROM achievements ORDER BY id LIMIT 2")]

    def test_the_catalogue_shows_how_many_times_each_was_awarded(self):
        first, second = self.ids()
        self.award(self.ana, first, datetime.date.today())
        self.award(self.bea, first, datetime.date.today())
        by_id = {a["id"]: a for a in self.admin("GET", "/achievements").json()}
        self.assertEqual((by_id[first]["awarded"], by_id[second]["awarded"]), (2, 0))
        self.assertFalse(by_id[first]["has_image"])

    def test_titles_and_messages_can_be_edited(self):
        first = self.ids()[0]
        done = self.admin("PATCH", f"/achievements/{first}", json={"title": "New title"}).json()
        self.assertEqual(done["title"], "New title")
        self.assertEqual(self.admin("PATCH", "/achievements/99999", json={"title": "x"}).status_code, 404)

    def test_awarded_achievements_are_listed_filtered_sorted_and_paged(self):
        first, second = self.ids()
        today = datetime.date.today()
        mine = self.award(self.ana, first, today, "celeste")
        self.award(self.bea, second, today - timedelta(days=1))
        listing = self.admin("GET", "/user-achievements").json()
        self.assertEqual(listing["total"], 2)
        self.assertEqual(listing["items"][0]["id"], mine)  # newest date first
        self.assertEqual((listing["items"][0]["user"], listing["items"][0]["game"]), ("ana", "Celeste"))
        self.assertEqual([i["user"] for i in self.admin("GET", "/user-achievements", params={"user_id": self.bea}).json()["items"]], ["bea"])
        self.assertEqual(self.admin("GET", "/user-achievements", params={"achievement_id": first}).json()["total"], 1)
        self.assertEqual(self.admin("GET", "/user-achievements", params={"game_id": "celeste"}).json()["total"], 1)
        self.assertEqual(self.admin("GET", "/user-achievements", params={"season": 1999}).json()["total"], 0)
        self.assertEqual(len(self.admin("GET", "/user-achievements", params={"limit": 1}).json()["items"]), 1)
        self.assertEqual(self.admin("GET", "/user-achievements", params={"sort": "x"}).status_code, 422)

    def test_the_date_of_an_award_can_change_and_its_year_decides_the_season(self):
        award = self.award(self.ana, self.ids()[0], datetime.date.today())
        done = self.admin("PATCH", f"/user-achievements/{award}", json={"date": "2024-02-03"}).json()
        self.assertEqual((done["date"], done["season"]), ("2024-02-03", 2024))
        self.assertEqual(self.admin("PATCH", "/user-achievements/99999", json={"date": "2024-01-01"}).status_code, 404)

    def test_an_award_can_be_revoked(self):
        award = self.award(self.ana, self.ids()[0], datetime.date.today())
        self.assertEqual(self.admin("DELETE", f"/user-achievements/{award}").status_code, 200)
        self.assertEqual(self.admin("DELETE", f"/user-achievements/{award}").status_code, 404)
        self.assertEqual(self.admin("GET", "/user-achievements").json()["total"], 0)
