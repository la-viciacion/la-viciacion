"""Timers and manual sessions through real requests (MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta

from sqlalchemy import text

from src.utils import seasons
from tests.api_support import ApiTestCase


def ago(**delta) -> datetime.datetime:
    """A moment in the past, to the second. Tests keep to a few hours so they stay in the running season."""
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


def iso(moment: datetime.datetime) -> str:
    return moment.isoformat()


class TimerTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.root = self.user("root", admin=True)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")

    def start(self, user="ana", user_id=None, game="celeste", platform="pc", **body):
        user_id = user_id or {"ana": self.ana, "bea": self.bea, "root": self.root}[user]
        return self.api("POST", "/timers/start", as_user=user, json={"user_id": user_id, "game_id": game, "platform": platform, **body})

    def manual(self, as_user="ana", start=None, end=None, game="celeste", platform="pc", **body):
        start = start or ago(hours=3)
        end = end or start + timedelta(hours=1)
        return self.api("POST", "/timers/manual", as_user=as_user,
                        json={"game_id": game, "platform": platform, "start_time": iso(start), "end_time": iso(end), **body})

    def finish_and_rewind(self, timer_id, user="ana", user_id=None):
        """Stops the timer and moves it two hours back, so the next one does not start in the same second
        (the table holds seconds, and one user cannot have two sessions of a game starting at the same one)."""
        user_id = user_id or self.ana
        self.assertEqual(self.api("POST", f"/timers/stop/{timer_id}", as_user=user, params={"user_id": user_id}).status_code, 200)
        with self.engine.begin() as conn:
            conn.execute(text(
                "UPDATE game_timers SET start_time = start_time - INTERVAL 2 HOUR, end_time = end_time - INTERVAL 2 HOUR WHERE id = :i"), {"i": timer_id})

    def library(self, user_id):
        return self.rows("SELECT game_id, platform, season FROM users_games WHERE user_id = :u ORDER BY id", u=user_id)


class StartTimerTests(TimerTestCase):
    def test_it_starts_a_running_timer_and_opens_the_library_entry(self):
        response = self.start()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["is_active"])
        self.assertEqual((body["user_id"], body["game_id"], body["platform"]), (self.ana, "celeste", "pc"))
        self.assertEqual(body["season"], seasons.current())
        self.assertEqual(self.library(self.ana), [("celeste", "pc", seasons.current())])

    def test_the_group_is_told_about_a_game_only_the_first_time_in_a_season(self):
        first = self.start().json()["id"]
        _, _, new_game = self.background["after_timer_start"].call_args.args
        self.assertEqual(new_game, "celeste")
        self.finish_and_rewind(first)
        self.start()
        self.assertIsNone(self.background["after_timer_start"].call_args.args[2])

    def test_the_same_game_on_another_platform_is_a_new_entry_but_not_news(self):
        self.finish_and_rewind(self.start().json()["id"])
        self.start(platform="switch")
        self.assertIsNone(self.background["after_timer_start"].call_args.args[2])
        self.assertEqual([r[1] for r in self.library(self.ana)], ["pc", "switch"])

    def test_one_timer_at_a_time(self):
        self.start()
        again = self.start(game="hades")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 1)

    def test_the_same_game_started_twice_in_the_same_second_is_a_conflict_not_a_crash(self):
        """A timer never starts before the user's last session ended, so one that ends ahead of the clock
        decides the second the next timer starts in. A session of that game that starts at that very second
        (what a retried start request leaves behind) must give a 409, not a 500."""
        ahead = datetime.datetime.now().replace(microsecond=0) + timedelta(seconds=40)
        self.session(self.ana, "celeste", ahead, 0)
        clash = self.start()
        self.assertEqual((clash.status_code, clash.json()["detail"]), (409, "Ya tienes un timer de ese juego que empieza a esa hora"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 1)
        self.assertEqual(self.start(game="hades").status_code, 200)  # another game starts at that second without trouble

    def test_a_timer_never_starts_before_the_last_session_ended(self):
        end = datetime.datetime.now().replace(microsecond=0) + timedelta(seconds=40)
        self.assertEqual(self.manual(start=end - timedelta(hours=1), end=end).status_code, 201)
        started = datetime.datetime.fromisoformat(self.start(game="hades").json()["start_time"])
        self.assertEqual(started, end)

    def test_unknown_game_user_and_platform_are_refused(self):
        self.assertEqual(self.start(game="nope").status_code, 404)
        self.assertEqual(self.start(user_id=9999, user="root").status_code, 404)
        self.assertEqual(self.start(platform="atari-9000").status_code, 400)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)

    def test_a_player_cannot_start_a_timer_for_somebody_else_but_an_admin_can(self):
        self.assertEqual(self.api("POST", "/timers/start", as_user="ana",
                                  json={"user_id": self.bea, "game_id": "celeste", "platform": "pc"}).status_code, 403)
        self.assertEqual(self.api("POST", "/timers/start", as_user="root",
                                  json={"user_id": self.bea, "game_id": "celeste", "platform": "pc"}).status_code, 200)

    def test_it_needs_a_login(self):
        self.assertEqual(self.api("POST", "/timers/start", json={"user_id": self.ana, "game_id": "celeste"}).status_code, 401)

    def test_notes_are_kept(self):
        self.assertEqual(self.start(notes="co-op with Bea").json()["notes"], "co-op with Bea")


class ActiveStopCancelTests(TimerTestCase):
    def test_no_timer_running_is_reported_as_such(self):
        body = self.api("GET", f"/timers/active/{self.ana}", as_user="ana").json()
        self.assertEqual(body, {"is_active": False, "timer": None, "score": None})

    def test_the_running_timer_is_reported(self):
        timer_id = self.start().json()["id"]
        body = self.api("GET", f"/timers/active/{self.ana}", as_user="ana").json()
        self.assertTrue(body["is_active"])
        self.assertEqual(body["timer"]["id"], timer_id)

    def test_somebody_else_cannot_see_it_but_an_admin_can(self):
        self.start()
        self.assertEqual(self.api("GET", f"/timers/active/{self.ana}", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", f"/timers/active/{self.ana}", as_user="root").status_code, 200)

    def test_stopping_records_the_end_and_the_duration_and_schedules_the_follow_ups(self):
        timer_id = self.start().json()["id"]
        stopped = self.api("POST", f"/timers/stop/{timer_id}", as_user="ana", params={"user_id": self.ana}).json()
        self.assertFalse(stopped["is_active"])
        self.assertIsNotNone(stopped["end_time"])
        self.assertGreaterEqual(stopped["duration_seconds"], 0)
        self.background["after_session_change"].assert_called_once()
        user, silent, ranking_before = self.background["after_session_change"].call_args.args
        self.assertEqual((user, silent), (self.ana, False))
        self.assertIsInstance(ranking_before, dict)
        game_id, _, duration = self.background["after_session_change"].call_args.kwargs["stopped"]
        self.assertEqual((game_id, duration), ("celeste", stopped["duration_seconds"]))  # what only a real timer can earn
        self.background["after_timer_stop"].assert_called_once_with(self.ana, "celeste", stopped["duration_seconds"])

    def test_a_timer_started_ahead_of_the_clock_stops_with_zero_not_negative_time(self):
        end = datetime.datetime.now().replace(microsecond=0) + timedelta(seconds=45)
        self.manual(start=end - timedelta(hours=1), end=end)
        timer_id = self.start(game="hades").json()["id"]
        stopped = self.api("POST", f"/timers/stop/{timer_id}", as_user="ana", params={"user_id": self.ana}).json()
        self.assertEqual(stopped["duration_seconds"], 0)

    def test_a_timer_stops_once(self):
        timer_id = self.start().json()["id"]
        self.api("POST", f"/timers/stop/{timer_id}", as_user="ana", params={"user_id": self.ana})
        self.assertEqual(self.api("POST", f"/timers/stop/{timer_id}", as_user="ana", params={"user_id": self.ana}).status_code, 404)

    def test_stopping_needs_the_owner_or_an_admin(self):
        timer_id = self.start().json()["id"]
        self.assertEqual(self.api("POST", f"/timers/stop/{timer_id}", as_user="bea", params={"user_id": self.ana}).status_code, 403)
        # claiming to be the owner does not help: the timer is looked up by owner
        self.assertEqual(self.api("POST", f"/timers/stop/{timer_id}", as_user="bea", params={"user_id": self.bea}).status_code, 404)
        self.assertEqual(self.api("POST", f"/timers/stop/{timer_id}", as_user="root", params={"user_id": self.ana}).status_code, 200)

    def test_cancelling_leaves_no_trace(self):
        timer_id = self.start().json()["id"]
        response = self.api("DELETE", f"/timers/cancel/{timer_id}", as_user="ana", params={"user_id": self.ana})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)
        self.assertEqual(self.library(self.ana), [])  # the entry the start created is not left empty
        self.background["after_timer_stop"].assert_called_once_with(self.ana, "celeste", None)

    def test_cancelling_keeps_the_entry_when_the_user_has_other_sessions_there(self):
        self.assertEqual(self.manual().status_code, 201)
        timer_id = self.start().json()["id"]
        self.api("DELETE", f"/timers/cancel/{timer_id}", as_user="ana", params={"user_id": self.ana})
        self.assertEqual(self.library(self.ana), [("celeste", "pc", seasons.current())])

    def test_cancelling_needs_the_owner_or_an_admin(self):
        timer_id = self.start().json()["id"]
        self.assertEqual(self.api("DELETE", f"/timers/cancel/{timer_id}", as_user="bea", params={"user_id": self.ana}).status_code, 403)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 1)


class HistoryTests(TimerTestCase):
    def setUp(self):
        super().setUp()
        self.session(self.ana, "celeste", ago(hours=9), 60, "pc")
        self.session(self.ana, "hades", ago(hours=6), 30, "switch")
        self.session(self.ana, "celeste", ago(hours=3), 45, "switch")
        self.session(self.bea, "celeste", ago(hours=2), 20, "pc")

    def test_the_history_is_newest_first_and_only_the_users(self):
        body = self.api("GET", f"/timers/history/{self.ana}", as_user="ana").json()
        self.assertEqual([t["duration_seconds"] for t in body], [45 * 60, 30 * 60, 60 * 60])

    def test_it_can_be_filtered_by_game_and_limited(self):
        celeste = self.api("GET", f"/timers/history/{self.ana}", as_user="ana", params={"game_id": "celeste"}).json()
        self.assertEqual([t["game_id"] for t in celeste], ["celeste", "celeste"])
        self.assertEqual(len(self.api("GET", f"/timers/history/{self.ana}", as_user="ana", params={"limit": 1}).json()), 1)

    def test_the_limit_has_bounds(self):
        for limit in (0, 501):
            self.assertEqual(self.api("GET", f"/timers/history/{self.ana}", as_user="ana", params={"limit": limit}).status_code, 422)

    def test_only_the_owner_or_an_admin_reads_a_history(self):
        self.assertEqual(self.api("GET", f"/timers/history/{self.ana}", as_user="bea").status_code, 403)
        self.assertEqual(self.api("GET", f"/timers/history/{self.ana}", as_user="root").status_code, 200)

    def test_the_grouped_history_has_one_row_per_game_newest_game_first(self):
        page = self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana").json()
        self.assertEqual(page["total_games"], 2)
        first, second = page["groups"]
        self.assertEqual((first["game_id"], first["game_name"], first["session_count"], first["total_seconds"]),
                         ("celeste", "Celeste", 2, 105 * 60))
        self.assertEqual(first["platforms"], ["switch", "pc"])  # most recently used first
        self.assertEqual(first["platform"], "switch")
        self.assertEqual([s["duration_seconds"] for s in first["sessions"]], [45 * 60, 60 * 60])
        self.assertEqual((second["game_id"], second["session_count"]), ("hades", 1))

    def test_the_grouped_history_pages_and_limits_sessions(self):
        page = self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana", params={"limit": 1, "offset": 1}).json()
        self.assertEqual([g["game_id"] for g in page["groups"]], ["hades"])
        self.assertEqual(page["total_games"], 2)
        limited = self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana", params={"sessions_per_game": 1}).json()
        self.assertEqual(len(limited["groups"][0]["sessions"]), 1)
        self.assertEqual(limited["groups"][0]["session_count"], 2)  # the count is of all of them

    def test_the_grouped_history_marks_the_games_completed_this_season(self):
        self.library_entry(self.ana, "celeste", ago(days=0).date(), "pc", completed=1)
        groups = {g["game_id"]: g for g in self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana").json()["groups"]}
        self.assertTrue(groups["celeste"]["completed"])
        self.assertFalse(groups["hades"]["completed"])

    def test_the_grouped_history_ignores_a_running_timer(self):
        self.start_for_ana = self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "hades", "platform": "pc"})
        page = self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana").json()
        self.assertEqual({g["game_id"]: g["session_count"] for g in page["groups"]}, {"celeste": 2, "hades": 1})

    def test_the_grouped_history_has_bounds(self):
        for params in ({"limit": 0}, {"limit": 51}, {"offset": -1}, {"sessions_per_game": 0}, {"sessions_per_game": 51}):
            self.assertEqual(self.api("GET", f"/timers/history/{self.ana}/grouped", as_user="ana", params=params).status_code, 422, params)

    def test_the_platforms_of_a_game_come_from_sessions_and_the_library(self):
        self.library_entry(self.ana, "hades", ago(hours=1).date(), "pc")
        body = self.api("GET", f"/timers/history/{self.ana}/platforms/hades", as_user="ana").json()
        self.assertEqual(body, {"has_history": True, "platforms": ["switch", "pc"]})
        nothing = self.api("GET", f"/timers/history/{self.ana}/platforms/unplayed", as_user="ana").json()
        self.assertEqual(nothing, {"has_history": False, "platforms": []})

    def test_a_game_with_sessions_but_no_platform_still_has_history(self):
        self.session(self.bea, "hades", ago(hours=5), 10, platform=None)
        body = self.api("GET", f"/timers/history/{self.bea}/platforms/hades", as_user="bea").json()
        self.assertEqual(body, {"has_history": True, "platforms": []})

    def test_the_platform_listing_is_private_too(self):
        self.assertEqual(self.api("GET", f"/timers/history/{self.ana}/platforms/hades", as_user="bea").status_code, 403)


class ManualSessionTests(TimerTestCase):
    def test_it_records_a_finished_session_and_its_library_entry_without_announcing(self):
        start = ago(hours=3)
        response = self.manual(start=start, end=start + timedelta(minutes=90), notes="speedrun")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertFalse(body["is_active"])
        self.assertEqual((body["duration_seconds"], body["notes"], body["platform"]), (90 * 60, "speedrun", "pc"))
        self.assertEqual(self.library(self.ana), [("celeste", "pc", seasons.current())])
        self.background["after_session_change"].assert_called_once_with(self.ana, True)  # silent
        self.background["after_timer_start"].assert_not_called()

    def test_the_time_rules(self):
        now = datetime.datetime.now().replace(microsecond=0)
        cases = {
            "end before start": (ago(hours=2), ago(hours=3)),
            "end equal to start": (ago(hours=2), ago(hours=2)),
            "ends in the future": (ago(hours=1), now + timedelta(hours=1)),
            "longer than 24 hours": (ago(hours=30), ago(hours=1)),
        }
        for name, (start, end) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.manual(start=start, end=end).status_code, 400)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)

    def test_it_may_end_a_minute_ahead_of_the_clock(self):
        end = datetime.datetime.now().replace(microsecond=0) + timedelta(seconds=30)
        self.assertEqual(self.manual(start=end - timedelta(hours=1), end=end).status_code, 201)

    def test_a_closed_season_is_frozen_for_players_but_not_for_admins(self):
        last_year = datetime.datetime(seasons.current() - 1, 6, 1, 20, 0)
        self.assertEqual(self.manual(start=last_year, end=last_year + timedelta(hours=1)).status_code, 400)
        self.assertEqual(self.manual(as_user="root", start=last_year, end=last_year + timedelta(hours=1)).status_code, 201)

    def test_it_cannot_overlap_another_session_of_the_same_user(self):
        start = ago(hours=5)
        self.assertEqual(self.manual(start=start, end=start + timedelta(hours=2)).status_code, 201)
        clash = self.manual(game="hades", start=start + timedelta(hours=1), end=start + timedelta(hours=3))
        self.assertEqual(clash.status_code, 409)
        self.assertIn("Celeste", clash.json()["detail"])
        touching = self.manual(game="hades", start=start + timedelta(hours=2), end=start + timedelta(hours=3))
        self.assertEqual(touching.status_code, 201)

    def test_it_cannot_overlap_a_running_timer(self):
        self.start()
        ends_ahead_of_the_timer = datetime.datetime.now().replace(microsecond=0) + timedelta(seconds=30)
        clash = self.manual(start=ago(hours=1), end=ends_ahead_of_the_timer)
        self.assertEqual(clash.status_code, 409)

    def test_other_users_sessions_do_not_matter(self):
        start = ago(hours=5)
        self.manual(as_user="bea", start=start, end=start + timedelta(hours=2))
        self.assertEqual(self.manual(start=start, end=start + timedelta(hours=2)).status_code, 201)

    def test_unknown_game_and_platform_are_refused(self):
        self.assertEqual(self.manual(game="nope").status_code, 404)
        self.assertEqual(self.manual(platform="atari-9000").status_code, 400)

    def test_notes_have_a_limit(self):
        self.assertEqual(self.manual(notes="x" * 501).status_code, 422)
        self.assertEqual(self.manual(notes="x" * 500).status_code, 201)

    def test_a_player_enters_only_their_own_sessions_and_an_admin_anybody_s(self):
        start = ago(hours=3)
        body = {"game_id": "celeste", "platform": "pc", "start_time": iso(start), "end_time": iso(start + timedelta(hours=1)), "user_id": self.bea}
        self.assertEqual(self.api("POST", "/timers/manual", as_user="ana", json=body).status_code, 403)
        done = self.api("POST", "/timers/manual", as_user="root", json=body)
        self.assertEqual((done.status_code, done.json()["user_id"]), (201, self.bea))


class EditSessionTests(TimerTestCase):
    def setUp(self):
        super().setUp()
        self.start_at = ago(hours=6)
        self.session_id = self.manual(start=self.start_at, end=self.start_at + timedelta(hours=1)).json()["id"]
        self.background["after_session_change"].reset_mock()

    def patch(self, as_user="ana", session_id=None, **body):
        return self.api("PATCH", f"/timers/{session_id or self.session_id}", as_user=as_user, json=body)

    def test_it_changes_times_and_recomputes_the_duration(self):
        response = self.patch(end_time=iso(self.start_at + timedelta(hours=2)))
        self.assertEqual((response.status_code, response.json()["duration_seconds"]), (200, 2 * 3600))
        self.background["after_session_change"].assert_called_once_with(self.ana, True)

    def test_it_changes_the_notes_and_can_clear_them(self):
        self.assertEqual(self.patch(notes="first try").json()["notes"], "first try")
        self.assertIsNone(self.patch(notes=None).json()["notes"])

    def test_moving_it_to_another_platform_moves_the_library_entry(self):
        self.assertEqual(self.patch(platform="switch").status_code, 200)
        self.assertEqual([r[1] for r in self.library(self.ana)], ["switch"])  # the empty "pc" entry is not left behind

    def test_the_old_entry_stays_if_it_has_other_sessions(self):
        self.manual(start=ago(hours=4), end=ago(hours=3))
        self.patch(platform="switch")
        self.assertEqual(sorted(r[1] for r in self.library(self.ana)), ["pc", "switch"])

    def test_the_time_rules_apply_to_edits_too(self):
        self.assertEqual(self.patch(end_time=iso(self.start_at - timedelta(minutes=1))).status_code, 400)
        self.assertEqual(self.patch(end_time=iso(self.start_at + timedelta(hours=30))).status_code, 400)

    def test_it_cannot_be_moved_onto_another_session(self):
        other = ago(hours=3)
        self.manual(game="hades", start=other, end=other + timedelta(hours=1))
        self.assertEqual(self.patch(end_time=iso(other + timedelta(minutes=10))).status_code, 409)

    def test_it_does_not_clash_with_itself(self):
        self.assertEqual(self.patch(start_time=iso(self.start_at + timedelta(minutes=5))).status_code, 200)

    def test_an_invalid_platform_is_refused(self):
        self.assertEqual(self.patch(platform="atari-9000").status_code, 400)

    def test_a_running_timer_cannot_be_edited(self):
        self.api("DELETE", f"/timers/{self.session_id}", as_user="ana")
        timer_id = self.start().json()["id"]
        self.assertEqual(self.patch(session_id=timer_id, notes="x").status_code, 409)

    def test_unknown_session_and_other_people_s_sessions(self):
        self.assertEqual(self.patch(session_id=999999, notes="x").status_code, 404)
        self.assertEqual(self.patch(as_user="bea", notes="x").status_code, 403)
        self.assertEqual(self.patch(as_user="root", notes="by an admin").status_code, 200)

    def test_a_session_of_a_closed_season_is_frozen_for_its_owner(self):
        old = self.session(self.ana, "hades", datetime.datetime(seasons.current() - 1, 3, 1, 20, 0), 60)
        self.assertEqual(self.patch(session_id=old, notes="x").status_code, 400)
        self.assertEqual(self.patch(as_user="root", session_id=old, notes="fixed").status_code, 200)

    def test_it_cannot_be_moved_out_of_the_running_season(self):
        last_year = datetime.datetime(seasons.current() - 1, 12, 30, 20, 0)
        self.assertEqual(self.patch(start_time=iso(last_year), end_time=iso(last_year + timedelta(hours=1))).status_code, 400)


class DeleteSessionTests(TimerTestCase):
    def setUp(self):
        super().setUp()
        start = ago(hours=4)
        self.session_id = self.manual(start=start, end=start + timedelta(hours=1)).json()["id"]
        self.background["after_session_change"].reset_mock()

    def test_it_removes_the_session_and_schedules_the_follow_up(self):
        response = self.api("DELETE", f"/timers/{self.session_id}", as_user="ana")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM game_timers"), 0)
        self.background["after_session_change"].assert_called_once_with(self.ana, True)

    def test_only_the_owner_or_an_admin_can_delete(self):
        self.assertEqual(self.api("DELETE", f"/timers/{self.session_id}", as_user="bea").status_code, 403)
        self.assertEqual(self.api("DELETE", f"/timers/{self.session_id}", as_user="root").status_code, 200)

    def test_unknown_and_running_ones(self):
        self.assertEqual(self.api("DELETE", "/timers/999999", as_user="ana").status_code, 404)
        self.api("DELETE", f"/timers/{self.session_id}", as_user="ana")
        timer_id = self.start().json()["id"]
        self.assertEqual(self.api("DELETE", f"/timers/{timer_id}", as_user="ana").status_code, 409)

    def test_a_closed_season_cannot_be_deleted_by_its_owner(self):
        old = self.session(self.ana, "hades", datetime.datetime(seasons.current() - 1, 3, 1, 20, 0), 60)
        self.assertEqual(self.api("DELETE", f"/timers/{old}", as_user="ana").status_code, 400)
        self.assertEqual(self.api("DELETE", f"/timers/{old}", as_user="root").status_code, 200)


class NowPlayingTests(TimerTestCase):
    def playing(self, as_user="bea"):
        return self.api("GET", "/timers/now-playing", as_user=as_user)

    def rewind(self, hours, user_id):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE game_timers SET start_time = start_time - INTERVAL :h HOUR WHERE user_id = :u AND is_active = 1"),
                         {"h": hours, "u": user_id})

    def test_nobody_playing_is_an_empty_list(self):
        response = self.playing()
        self.assertEqual((response.status_code, response.json()), (200, []))

    def test_it_lists_who_is_playing_what_for_every_logged_in_player(self):
        self.start(user="ana", game="celeste", platform="pc")
        body = self.playing().json()
        self.assertEqual(len(body), 1)
        self.assertEqual((body[0]["user_id"], body[0]["name"], body[0]["game_name"], body[0]["platform"], body[0]["stale"]),
                         (self.ana, "Ana", "Celeste", "pc", False))
        self.assertIn("start_time", body[0])
        self.assertEqual(self.api("GET", "/timers/now-playing").status_code, 401)

    def test_finished_timers_inactive_players_and_the_emergency_account_are_left_out(self):
        timer = self.start(user="ana").json()["id"]
        self.api("POST", f"/timers/stop/{timer}", as_user="ana", params={"user_id": self.ana})
        self.start(user="bea", game="hades")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE users SET is_active = 0 WHERE id = :i"), {"i": self.bea})
        self.assertEqual(self.playing(as_user="root").json(), [])

    def test_after_six_hours_a_timer_is_stale_and_comes_last(self):
        self.start(user="ana", game="celeste")
        self.rewind(7, self.ana)
        self.start(user="bea", game="hades")
        body = self.playing(as_user="root").json()
        self.assertEqual([(p["name"], p["stale"]) for p in body], [("Bea", False), ("Ana", True)])

    def test_the_latest_started_comes_first(self):
        self.start(user="ana", game="celeste")
        self.rewind(2, self.ana)
        self.start(user="bea", game="hades")
        self.assertEqual([p["name"] for p in self.playing(as_user="root").json()], ["Bea", "Ana"])

    def test_a_player_can_hide_from_the_others_but_not_from_themselves(self):
        self.start(user="ana", game="celeste")
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"show_playing": False})
        self.assertEqual(self.playing(as_user="bea").json(), [])
        self.assertEqual([p["name"] for p in self.playing(as_user="ana").json()], ["Ana"])
        self.api("PATCH", "/users/ana/settings", as_user="ana", json={"show_playing": True})
        self.assertEqual(len(self.playing(as_user="bea").json()), 1)
