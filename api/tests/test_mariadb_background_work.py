"""What the application does after it has answered: achievements, completion and ranking announcements
(MariaDB required, see api_support.py). The real functions of `utils/actions.py` and `crud/achievements.py` run
against the database; Telegram is replaced by a recorder, so a test reads what the group would have been told."""
import asyncio
import datetime
from datetime import timedelta
from unittest import mock

from sqlalchemy import text

from src.crud import users as users_crud
from src.database import database, models
from src.utils import actions, my_utils, seasons
from src.utils.achievements import AchievementsElems as E
from tests.api_support import ApiTestCase

YEAR = datetime.date.today().year


def at(month: int, day: int, hour: int = 20, minute: int = 0) -> datetime.datetime:
    """A moment of the running season (it may be in the future early in the year: the checks do not mind)."""
    return datetime.datetime(YEAR, month, day, hour, minute)


class WorkTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.sent = []

        async def send_message(message, silent=False, **kwargs):
            self.sent.append({"text": message, "silent": silent, **kwargs})

        self.admin_alerts = []

        async def send_to_admins(db, message):
            self.admin_alerts.append(message)

        for patcher in (
            mock.patch.object(my_utils, "send_message", new=send_message),
            mock.patch.object(my_utils, "send_message_to_admins", new=send_to_admins),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.engine.begin() as conn:  # some are special or secret: it is not what these tests are about
            conn.execute(text("UPDATE achievements SET valid_from_season = 2023, special = 0, secret = 0"))
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        for game_id in ("celeste", "hades", "tetris"):
            self.game(game_id)

    # --- running the real work

    def check(self, user_ids=None, silent=False, **kwargs):
        async def run():
            with database.SessionLocal() as db:
                await actions.check_users(db, silent=silent, user_ids=user_ids, **kwargs)
        asyncio.run(run())

    def check_one(self, username="ana", silent=False):
        async def run():
            with database.SessionLocal() as db:
                user = db.query(models.User).filter_by(username=username).one()
                await actions.check_user(db, user, silent=silent)
        asyncio.run(run())

    def announce_lost_streaks(self, today):
        async def run():
            with database.SessionLocal() as db:
                await actions.announce_lost_streaks(db, today)
        asyncio.run(run())

    def awarded(self, user_id=None) -> dict:
        """{achievement key: (date, game_id)} of a user, as stored."""
        rows = self.rows(
            "SELECT a.`key`, ua.date, ua.game_id FROM users_achievements ua JOIN achievements a ON a.id = ua.achievement_id "
            "WHERE ua.user_id = :u", u=user_id or self.ana)
        return {key: (str(date), game) for key, date, game in rows}

    def titles_sent(self):
        return [m["text"].split("\n")[0].strip("🏆") for m in self.sent]

    def play_days(self, user_id, days, minutes=30, game="celeste", month=3, start_day=1):
        for offset in range(days):
            self.session(user_id, game, at(month, start_day + offset), minutes)


class DaysAndStreaksTests(WorkTestCase):
    def test_seven_days_unlock_the_days_and_the_streak_achievements_dated_by_the_day_they_were_reached(self):
        self.play_days(self.ana, 7)
        self.check_one()
        got = self.awarded()
        self.assertEqual(got["PLAYED_7_DAYS"][0], f"{YEAR}-03-07")
        self.assertIn("STREAK_7_DAYS", got)
        self.assertNotIn("PLAYED_15_DAYS", got)

    def test_each_one_is_announced_with_the_player_s_name_and_the_title(self):
        self.play_days(self.ana, 7)
        self.check_one()
        announced = {m["text"] for m in self.sent}
        seven_days = next(t for t in announced if E.PLAYED_7_DAYS.value["title"] in t)
        self.assertIn("Ana", seven_days)
        self.assertTrue(all(m["silent"] is False for m in self.sent))

    def test_a_silent_check_stores_the_achievements_and_tells_the_sender_to_stay_quiet(self):
        self.play_days(self.ana, 7)
        self.check_one(silent=True)
        self.assertIn("PLAYED_7_DAYS", self.awarded())
        self.assertTrue(self.sent and all(m["silent"] is True for m in self.sent))

    def test_sessions_under_ten_minutes_do_not_make_a_played_day(self):
        self.play_days(self.ana, 7, minutes=5)
        self.check_one()
        got = self.awarded()
        self.assertNotIn("PLAYED_7_DAYS", got)

    def test_a_gap_breaks_the_streak_not_the_count_of_days(self):
        self.play_days(self.ana, 3)
        self.play_days(self.ana, 4, start_day=10)
        self.check_one()
        got = self.awarded()
        self.assertIn("PLAYED_7_DAYS", got)
        self.assertNotIn("STREAK_7_DAYS", got)

    def test_running_the_check_again_changes_nothing_and_announces_nothing(self):
        self.play_days(self.ana, 7)
        self.check_one()
        before, messages = self.awarded(), len(self.sent)
        self.check_one()
        self.assertEqual((self.awarded(), len(self.sent)), (before, messages))

    def test_an_achievement_of_a_previous_season_does_not_block_this_one(self):
        key_id = self.scalar("SELECT id FROM achievements WHERE `key` = 'PLAYED_7_DAYS'")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) VALUES (:u, :a, :d)"),
                         {"u": self.ana, "a": key_id, "d": datetime.date(YEAR - 1, 6, 1)})
        self.play_days(self.ana, 7)
        self.check_one()
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_achievements WHERE user_id = :u AND achievement_id = :a", u=self.ana, a=key_id), 2)

    def test_the_lost_streak_is_announced_once_on_the_day_it_is_lost(self):
        today = datetime.date.today()
        for back in range(2, 14):  # twelve days, the last one two days ago
            self.session(self.ana, "celeste", datetime.datetime.combine(today - timedelta(days=back), datetime.time(20, 0)), 30)
        self.announce_lost_streaks(today)
        lost = [m["text"] for m in self.sent if "perder la racha" in m["text"]]
        self.assertEqual(len(lost), 1)
        self.assertIn("12 días", lost[0])
        self.sent.clear()
        self.announce_lost_streaks(today + timedelta(days=1))  # the day after: nothing more to say
        self.check_one()  # and a check of the achievements never announces it
        self.assertFalse([m for m in self.sent if "perder la racha" in m["text"]])


class TimeAndSessionTests(WorkTestCase):
    def test_hours_in_total_in_a_day_in_a_game_and_in_one_session(self):
        for day in (1, 2, 3, 4, 5):
            self.session(self.ana, "celeste", at(3, day, 9), 20 * 60)  # five sessions of 20 hours
        self.check_one()
        got = self.awarded()
        for key in ("PLAYED_100_HOURS", "PLAYED_4_HOURS_DAY", "PLAYED_8_HOURS_DAY", "PLAYED_12_HOURS_DAY", "PLAYED_16_HOURS_DAY",
                    "PLAYED_4_HOURS_SESSION", "PLAYED_8_HOURS_SESSION", "PLAYED_8_HOURS_GAME_DAY", "PLAYED_100_HOURS_GAME"):
            self.assertIn(key, got, key)
        self.assertNotIn("PLAYED_200_HOURS", got)
        self.assertEqual(got["PLAYED_100_HOURS_GAME"][1], "celeste")
        self.assertEqual(got["PLAYED_4_HOURS_DAY"][0], f"{YEAR}-03-01")  # the first day that reached it

    def test_the_message_of_a_game_achievement_names_the_game(self):
        for day in range(1, 6):
            self.session(self.ana, "celeste", at(3, day, 9), 20 * 60)
        self.check_one()
        text = next(m["text"] for m in self.sent if E.PLAYED_100_HOURS_GAME.value["title"] in m["text"])
        self.assertIn("Celeste", text)

    def test_a_timer_stopped_within_five_minutes_earns_opened_by_mistake(self):
        self.session(self.ana, "celeste", at(3, 1), 4)
        self.real_actions["after_session_change"](self.ana, False, None, stopped=("celeste", at(3, 1), 4 * 60))
        self.assertEqual(self.awarded()["PLAYED_LESS_5_MIN_SESSION"], (f"{YEAR}-03-01", "celeste"))

    def test_a_manual_or_edited_session_never_earns_it(self):
        self.session(self.ana, "celeste", at(3, 1), 4)
        self.check_one()
        self.real_actions["after_session_change"](self.ana, True)
        self.assertNotIn("PLAYED_LESS_5_MIN_SESSION", self.awarded())

    def test_a_timer_stopped_at_once_or_after_more_than_five_minutes_does_not(self):
        for seconds in (0, 5 * 60 + 1):
            self.real_actions["after_session_change"](self.ana, False, None, stopped=("celeste", at(3, 1), seconds))
        self.assertNotIn("PLAYED_LESS_5_MIN_SESSION", self.awarded())

    def test_playing_many_different_games_in_one_day(self):
        for n in range(5):
            self.game(f"extra-{n}")
            self.session(self.ana, f"extra-{n}", at(3, 1, 8 + 2 * n), 30)
        self.check_one()
        got = self.awarded()
        self.assertIn("PLAYED_5_GAMES_DAY", got)
        self.assertNotIn("PLAYED_10_GAMES_DAY", got)

    def test_a_new_year_session_and_the_early_and_late_hours(self):
        self.session(self.ana, "celeste", datetime.datetime(YEAR, 1, 1, 0, 30), 30)
        self.session(self.ana, "hades", at(3, 2, 5, 30), 30)
        self.session(self.ana, "tetris", at(3, 3, 3, 0), 30)
        self.check_one()
        got = self.awarded()
        for key in ("HAPPY_NEW_YEAR", "EARLY_RISER", "NOCTURNAL"):
            self.assertIn(key, got, key)
        self.assertEqual(got["EARLY_RISER"][0], f"{YEAR}-03-02")  # the column holds the date, not the time

    def test_other_hours_unlock_neither(self):
        self.session(self.ana, "celeste", at(3, 2, 12), 30)
        self.check_one()
        got = self.awarded()
        for key in ("EARLY_RISER", "NOCTURNAL", "HAPPY_NEW_YEAR"):
            self.assertNotIn(key, got)


class LibraryAchievementsTests(WorkTestCase):
    def test_ten_different_games_this_season(self):
        for n in range(10):
            self.game(f"g{n}")
            self.library_entry(self.ana, f"g{n}", datetime.date(YEAR, 3, 1))
        self.check_one()
        self.assertIn("PLAYED_10_GAMES", self.awarded())

    def test_the_same_game_on_two_platforms_counts_once(self):
        for n in range(9):
            self.game(f"g{n}")
            self.library_entry(self.ana, f"g{n}", datetime.date(YEAR, 3, 1))
        self.library_entry(self.ana, "g0", datetime.date(YEAR, 3, 2), "switch")
        self.check_one()
        self.assertNotIn("PLAYED_10_GAMES", self.awarded())

    def test_forty_two_completed_games(self):
        for n in range(42):
            self.game(f"c{n}")
            self.library_entry(self.ana, f"c{n}", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 2))
        self.check_one()
        got = self.awarded()
        self.assertIn("COMPLETED_42_GAMES", got)
        self.assertIn("PLAYED_42_GAMES", got)
        self.assertNotIn("COMPLETED_100_GAMES", got)


class TeamworkTests(WorkTestCase):
    def start_timers(self, *usernames):
        with database.SessionLocal() as db:
            for name in usernames:
                user = db.query(models.User).filter_by(username=name).one()
                db.add(models.GameTimer(user_id=user.id, game_id="celeste", start_time=datetime.datetime.now(), is_active=True, platform="pc"))
            db.commit()

    def team_check(self):
        """What starting a timer runs (after_timer_start): teamwork is not part of the general check."""
        async def run():
            with database.SessionLocal() as db:
                await actions.achievements.teamwork(db, silent=False)
        asyncio.run(run())

    def test_four_players_at_once_unlock_it_for_everybody_with_one_message(self):
        cai, dan = self.user("cai"), self.user("dan")
        self.start_timers("ana", "bea", "cai", "dan")
        self.team_check()
        for user_id in (self.ana, self.bea, cai, dan):
            self.assertIn("TEAMWORK", self.awarded(user_id), user_id)
        teamwork = [m["text"] for m in self.sent if E.TEAMWORK.value["title"] in m["text"]]
        self.assertEqual(len(teamwork), 1)
        self.assertIn("Ana, Bea, Cai y Dan", teamwork[0])

    def test_three_are_not_enough_and_a_repeat_stays_quiet(self):
        self.user("cai"), self.user("dan")
        self.start_timers("ana", "bea", "cai")
        self.team_check()
        self.assertEqual(self.sent, [])
        self.start_timers("dan")
        self.team_check()
        self.team_check()
        self.assertEqual(len([m for m in self.sent if E.TEAMWORK.value["title"] in m["text"]]), 1)

    def test_the_third_player_on_a_game_unlocks_all_together_for_the_three(self):
        cai = self.user("cai")
        self.start_timers("ana", "bea")
        now = datetime.datetime.now().replace(microsecond=0)  # as the database gives it back: with microseconds, a run at 02:00-06:00 dates an early riser from a text that does not parse
        self.real_actions["after_timer_start"](self.ana, now, None)
        self.assertNotIn("ALL_TOGETHER", self.awarded())
        self.start_timers("cai")
        self.real_actions["after_timer_start"](cai, now, None)
        for user_id in (self.ana, self.bea, cai):
            self.assertEqual(self.awarded(user_id)["ALL_TOGETHER"][1], "celeste", user_id)
        self.assertEqual(len([m for m in self.sent if E.ALL_TOGETHER.value["title"] in m["text"]]), 1)

    def test_a_disabled_player_does_not_count(self):
        self.user("cai"), self.user("dan", active=False)
        self.start_timers("ana", "bea", "cai", "dan")
        self.team_check()
        self.assertFalse([m for m in self.sent if E.TEAMWORK.value["title"] in m["text"]])

    def test_the_general_check_does_not_evaluate_it(self):
        self.user("cai"), self.user("dan")
        self.start_timers("ana", "bea", "cai", "dan")
        self.check()
        self.assertFalse([m for m in self.sent if E.TEAMWORK.value["title"] in m["text"]])


class CheckUsersTests(WorkTestCase):
    def test_only_the_asked_users_are_checked_and_never_a_disabled_one(self):
        self.user("off", active=False)
        off = self.scalar("SELECT id FROM users WHERE username = 'off'")
        for user_id in (self.ana, self.bea, off):
            self.play_days(user_id, 7, month=3 if user_id != off else 4)
        self.check(user_ids=[self.ana, off])
        self.assertIn("PLAYED_7_DAYS", self.awarded(self.ana))
        self.assertEqual(self.awarded(self.bea), {})
        self.assertEqual(self.awarded(off), {})

    def test_everybody_is_checked_when_no_ids_are_given(self):
        for user_id in (self.ana, self.bea):
            self.play_days(user_id, 7)
        self.check()
        self.assertTrue(self.awarded(self.ana) and self.awarded(self.bea))

    def test_one_failing_user_does_not_stop_the_rest_and_the_admins_are_told(self):
        self.play_days(self.bea, 7)
        real = actions.check_user

        async def flaky(db, user, **kwargs):
            if user.username == "ana":
                raise RuntimeError("boom")
            return await real(db, user, **kwargs)

        with mock.patch.object(actions, "check_user", new=flaky):
            self.check()
        self.assertIn("PLAYED_7_DAYS", self.awarded(self.bea))
        self.assertEqual(self.admin_alerts, ["Error checking achievements of: ana"])


class CompletionWorkTests(WorkTestCase):
    def test_completing_a_game_announces_it_with_the_time_and_the_average(self):
        entry = self.library_entry(self.ana, "celeste", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 5))
        self.session(self.ana, "celeste", at(3, 1), 90)
        self.session(self.ana, "celeste", at(3, 2), 30)
        self.real_actions["after_completion"](entry, False)
        message = self.sent[-1]
        self.assertIn("Ana acaba de completar su juego número 1", message["text"])
        self.assertIn("*Celeste* en 02h00m", message["text"])
        self.assertEqual((message["silent"], message["ai_use"]), (False, "completed_game"))

    def test_a_silent_completion_is_sent_silently(self):
        entry = self.library_entry(self.ana, "celeste", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 5))
        self.real_actions["after_completion"](entry, True)
        self.assertTrue(self.sent[-1]["silent"])

    def test_finishing_in_the_average_time_unlocks_just_in_time(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE games SET avg_time = 7200 WHERE id = 'celeste'"))
        entry = self.library_entry(self.ana, "celeste", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 5))
        self.session(self.ana, "celeste", at(3, 1), 120)
        self.real_actions["after_completion"](entry, False)
        self.assertIn("JUST_IN_TIME", self.awarded())

    def test_only_the_time_of_the_season_counts_towards_the_average(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE games SET avg_time = 7200 WHERE id = 'celeste'"))
        entry = self.library_entry(self.ana, "celeste", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 5))
        self.session(self.ana, "celeste", datetime.datetime(YEAR - 1, 11, 1, 20, 0), 60)  # last season's hour
        self.session(self.ana, "celeste", at(3, 1), 60)
        self.real_actions["after_completion"](entry, False)
        self.assertNotIn("JUST_IN_TIME", self.awarded())
        self.assertIn("*Celeste* en 01h00m", self.sent[-1]["text"])

    def test_a_game_far_from_the_average_does_not(self):
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE games SET avg_time = 36000 WHERE id = 'celeste'"))
        entry = self.library_entry(self.ana, "celeste", datetime.date(YEAR, 3, 1), completed=1, completed_date=datetime.date(YEAR, 3, 5))
        self.session(self.ana, "celeste", at(3, 1), 120)
        self.real_actions["after_completion"](entry, False)
        self.assertNotIn("JUST_IN_TIME", self.awarded())

    def test_a_vanished_entry_is_ignored(self):
        self.real_actions["after_completion"](999999, False)
        self.assertEqual(self.sent, [])


class StartAndStopWorkTests(WorkTestCase):
    def test_starting_a_game_for_the_first_time_this_season_tells_the_group(self):
        started = at(3, 4, 14)
        self.real_actions["after_timer_start"](self.ana, started, "celeste")
        self.assertTrue(any("Celeste" in m["text"] for m in self.sent))

    def test_a_timer_that_starts_early_in_the_morning_unlocks_early_riser_at_once(self):
        self.real_actions["after_timer_start"](self.ana, at(3, 4, 5, 15), None)
        self.assertIn("EARLY_RISER", self.awarded())
        self.assertNotIn("NOCTURNAL", self.awarded())

    def test_a_timer_started_on_the_release_day_of_its_game_unlocks_it_at_once(self):
        today = datetime.date.today()
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE games SET release_date = :d WHERE id = 'celeste'"), {"d": today})
        started = datetime.datetime.now().replace(microsecond=0)
        with database.SessionLocal() as db:
            db.add(models.GameTimer(user_id=self.ana, game_id="celeste", start_time=started, is_active=True, platform="pc"))
            db.commit()
        self.real_actions["after_timer_start"](self.ana, started, None)
        self.assertEqual(self.awarded()["RELEASE_DAY"][1], "celeste")

    def test_a_timer_that_starts_in_the_small_hours_unlocks_nocturnal(self):
        self.real_actions["after_timer_start"](self.ana, at(3, 4, 3, 0), None)
        self.assertIn("NOCTURNAL", self.awarded())

    def test_a_vanished_user_is_ignored(self):
        self.real_actions["after_timer_start"](999999, at(3, 4, 14), "celeste")
        self.assertEqual(self.awarded(), {})

    def test_stopping_a_timer_clears_its_notification_even_without_devices(self):
        self.real_actions["after_timer_stop"](self.ana, "celeste", 600)
        self.real_actions["after_timer_stop"](self.ana, "no-such-game", None)


class EditedSessionTests(WorkTestCase):
    def test_deleting_a_session_revokes_what_it_earned_without_telling_anybody(self):
        self.play_days(self.ana, 7)
        self.check_one()
        self.assertIn("STREAK_7_DAYS", self.awarded())
        with self.engine.begin() as conn:
            conn.execute(text("DELETE FROM game_timers WHERE user_id = :u ORDER BY start_time DESC LIMIT 1"), {"u": self.ana})
        self.sent.clear()
        self.real_actions["after_session_change"](self.ana, True, recalculate=[YEAR])
        got = self.awarded()
        self.assertNotIn("PLAYED_7_DAYS", got)
        self.assertNotIn("STREAK_7_DAYS", got)
        self.assertEqual(self.sent, [])

    def test_only_the_seasons_asked_for_are_worked_out_again(self):
        key_id = self.scalar("SELECT id FROM achievements WHERE `key` = 'PLAYED_30_DAYS'")
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO users_achievements (user_id, achievement_id, date) VALUES (:u, :a, :d)"),
                         {"u": self.ana, "a": key_id, "d": datetime.date(YEAR - 1, 6, 1)})
        self.real_actions["after_session_change"](self.ana, True, recalculate=[YEAR])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_achievements WHERE user_id = :u", u=self.ana), 1)
        self.real_actions["after_session_change"](self.ana, True, recalculate=[YEAR - 1])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_achievements WHERE user_id = :u", u=self.ana), 0)


class RankingAnnouncementTests(WorkTestCase):
    def test_overtaking_somebody_is_announced_after_the_session_that_did_it(self):
        self.session(self.ana, "celeste", at(3, 1), 120)
        self.session(self.bea, "celeste", at(3, 2), 60)
        with database.SessionLocal() as db:
            before = actions.ranking_snapshot(db)
        self.assertEqual(before["players"], [self.ana, self.bea])
        self.session(self.bea, "celeste", at(3, 3), 180)  # Bea now has 4 h against Ana's 2 h
        self.real_actions["after_session_change"](self.bea, False, before)
        ranking = [m["text"] for m in self.sent if "Bea" in m["text"] and "Ana" in m["text"]]
        self.assertTrue(ranking, [m["text"] for m in self.sent])

    def test_the_same_order_announces_nothing(self):
        self.session(self.ana, "celeste", at(3, 1), 120)
        self.session(self.bea, "celeste", at(3, 2), 60)
        with database.SessionLocal() as db:
            before = actions.ranking_snapshot(db)
        self.session(self.ana, "celeste", at(3, 4), 30)
        self.real_actions["after_session_change"](self.ana, False, before)
        self.assertFalse([m for m in self.sent if "Bea" in m["text"] and "Ana" in m["text"]])

    def test_a_silent_change_is_never_announced_as_a_ranking(self):
        self.session(self.ana, "celeste", at(3, 1), 120)
        self.session(self.bea, "celeste", at(3, 2), 60)
        with database.SessionLocal() as db:
            before = actions.ranking_snapshot(db)
        self.session(self.bea, "celeste", at(3, 3), 180)
        self.real_actions["after_session_change"](self.bea, True, before)
        self.assertTrue(all(m["silent"] for m in self.sent))

    def test_the_follow_up_checks_the_achievements_of_that_user_only(self):
        self.play_days(self.ana, 7)
        self.play_days(self.bea, 7, month=4)
        self.real_actions["after_session_change"](self.ana, True)
        self.assertIn("PLAYED_7_DAYS", self.awarded(self.ana))
        self.assertEqual(self.awarded(self.bea), {})

    def test_the_follow_up_checks_everybody_when_no_user_is_given(self):
        self.play_days(self.ana, 7)
        self.play_days(self.bea, 7, month=4)
        self.real_actions["after_session_change"](None, True)
        self.assertTrue(self.awarded(self.ana) and self.awarded(self.bea))

    def test_the_game_ranking_snapshot_lists_games_by_hours(self):
        self.session(self.ana, "hades", at(3, 1), 60)
        self.session(self.ana, "celeste", at(3, 2), 180)
        with database.SessionLocal() as db:
            self.assertEqual(actions.ranking_snapshot(db)["games"], ["celeste", "hades"])
