import datetime
import types
import unittest
from unittest import mock

from src.utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from src.crud import achievements as ach_module
from src.crud.achievements import Achievements
from src.database import models
from tests.sqlite_db import make_session

USER = types.SimpleNamespace(id=1, name="Ana")
YEAR = datetime.date.today().year


class AchievementCheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g1", name="Doom", slug="doom"))
        self.db.commit()
        self.ach = Achievements()
        self.ach.populate_achievements(self.db)
        self.sent = mock.AsyncMock()
        patcher = mock.patch.object(ach_module.utils, "send_message", self.sent)
        patcher.start()
        self.addCleanup(patcher.stop)

    def awarded(self):
        rows = (
            self.db.query(models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id)
            .join(models.UserAchievement, models.UserAchievement.achievement_id == models.Achievement.id)
            .all()
        )
        return {key: (date, game_id) for key, date, game_id in rows}

    def message(self, index=0):
        return self.sent.await_args_list[index].args[0]

    def days(self, n):
        first = datetime.date(YEAR, 1, 1)
        return [first + datetime.timedelta(days=i) for i in range(n)]

    async def test_played_days_unlock_every_threshold_reached_dated_at_the_day_that_reached_it(self):
        await self.ach.user_played_total_days(self.db, USER, self.days(31))
        got = self.awarded()
        self.assertEqual(set(got), {"PLAYED_7_DAYS", "PLAYED_15_DAYS", "PLAYED_30_DAYS"})
        self.assertEqual(got["PLAYED_7_DAYS"][0], self.days(7)[-1])
        self.assertEqual(got["PLAYED_30_DAYS"][0], self.days(30)[-1])
        self.assertEqual(self.sent.await_count, 3)

    async def test_nothing_is_unlocked_twice(self):
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(list(self.awarded()), ["PLAYED_7_DAYS"])
        self.assertEqual(self.sent.await_count, 1)

    async def test_below_the_first_threshold_nothing_happens(self):
        await self.ach.user_played_total_days(self.db, USER, self.days(6))
        self.assertEqual(self.awarded(), {})
        self.sent.assert_not_awaited()

    async def test_total_time_is_dated_the_day_the_running_total_crossed_each_threshold(self):
        rows = [
            (datetime.date(YEAR, 1, 10), 90 * 3600),
            (datetime.date(YEAR, 2, 1), None),
            (datetime.date(YEAR, 3, 5), 70 * 3600),
            (datetime.date(YEAR, 4, 1), 50 * 3600),
        ]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_day", return_value=rows):
            await self.ach.user_played_total_time(self.db, USER)
        got = self.awarded()
        self.assertEqual(set(got), {"PLAYED_100_HOURS", "PLAYED_200_HOURS"})
        self.assertEqual(got["PLAYED_100_HOURS"][0], datetime.date(YEAR, 3, 5))
        self.assertEqual(got["PLAYED_200_HOURS"][0], datetime.date(YEAR, 4, 1))

    async def test_total_time_without_data_does_nothing(self):
        await self.ach.user_played_total_time(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_each_streak_is_dated_the_day_a_run_reached_its_length(self):
        first_run = self.days(8)  # 1 to 8 January: reaches 7 on the 7th
        second_run = [datetime.date(YEAR, 2, 1) + datetime.timedelta(days=i) for i in range(16)]  # the best one
        await self.ach.user_streak(self.db, USER, first_run + second_run)
        got = self.awarded()
        self.assertEqual(set(got), {"STREAK_7_DAYS", "STREAK_15_DAYS"})
        self.assertEqual(got["STREAK_7_DAYS"][0], datetime.date(YEAR, 1, 7))
        self.assertEqual(got["STREAK_15_DAYS"][0], datetime.date(YEAR, 2, 15))

    async def test_a_streak_already_earned_is_not_awarded_again(self):
        await self.ach.user_streak(self.db, USER, self.days(7))
        await self.ach.user_streak(self.db, USER, self.days(7))
        self.assertEqual(self.sent.await_count, 1)

    def library_entry(self, game_id, started, completed=None, platform=None):
        self.db.add(
            models.UserGame(
                user_id=1, game_id=game_id, started_date=started, platform=platform,
                completed=1 if completed else 0, completed_date=completed,
            )
        )

    async def test_played_games_are_dated_the_day_the_nth_game_began(self):
        for n in range(10):
            self.library_entry(f"g{n}", datetime.date(YEAR, 1, 1) + datetime.timedelta(days=n * 2))
        # the same game on another platform is not another game
        self.library_entry("g0", datetime.date(YEAR, 6, 1), platform="switch")
        self.db.commit()
        await self.ach.user_played_total_games(self.db, USER)
        got = self.awarded()
        self.assertEqual(set(got), {"PLAYED_10_GAMES"})
        self.assertEqual(got["PLAYED_10_GAMES"][0], datetime.date(YEAR, 1, 19))

    async def test_nine_games_and_a_repeat_are_not_ten(self):
        for n in range(9):
            self.library_entry(f"g{n}", datetime.date(YEAR, 1, 1) + datetime.timedelta(days=n))
        self.library_entry("g0", datetime.date(YEAR, 6, 1), platform="switch")
        self.db.commit()
        await self.ach.user_played_total_games(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_completed_games_are_dated_the_day_the_nth_was_completed(self):
        for n in range(42):
            self.library_entry(f"g{n}", datetime.date(YEAR, 1, 1), completed=datetime.date(YEAR, 1, 1) + datetime.timedelta(days=41 - n))
        self.db.commit()
        await self.ach.user_completed_total_games(self.db, USER)
        got = self.awarded()
        self.assertEqual(set(got), {"COMPLETED_42_GAMES"})
        self.assertEqual(got["COMPLETED_42_GAMES"][0], datetime.date(YEAR, 1, 1) + datetime.timedelta(days=41))

    async def test_hours_in_a_game_are_dated_the_day_they_crossed_100_and_name_the_game(self):
        self.db.add(models.Game(id="g2", name="Hades", slug="hades"))
        self.db.commit()
        rows = [
            (datetime.date(YEAR, 3, 1), "g1", 50 * 3600),
            (datetime.date(YEAR, 2, 1), "g1", 60 * 3600),  # g1 crosses on 1 March
            (datetime.date(YEAR, 4, 1), "g2", 101 * 3600),  # g2 crosses later: not the one
            (datetime.date(YEAR, 1, 5), "g3", 40 * 3600),
        ]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_game_and_day", return_value=rows):
            await self.ach.user_played_hours_game(self.db, USER)
        got = self.awarded()
        self.assertEqual(got["PLAYED_100_HOURS_GAME"], (datetime.date(YEAR, 3, 1), "g1"))
        self.assertIn("Doom", self.message())
        self.assertEqual(self.sent.await_count, 1)

    async def test_the_first_game_to_cross_100_hours_wins_even_when_it_is_not_the_biggest(self):
        self.db.add(models.Game(id="g2", name="Hades", slug="hades"))
        self.db.commit()
        rows = [
            (datetime.date(YEAR, 2, 1), "g2", 100 * 3600),
            (datetime.date(YEAR, 3, 1), "g1", 300 * 3600),
        ]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_game_and_day", return_value=rows):
            await self.ach.user_played_hours_game(self.db, USER)
        self.assertEqual(self.awarded()["PLAYED_100_HOURS_GAME"], (datetime.date(YEAR, 2, 1), "g2"))

    async def test_99_hours_in_a_game_is_not_enough(self):
        rows = [(datetime.date(YEAR, 2, 1), "g1", 99 * 3600 + 3000)]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_game_and_day", return_value=rows):
            await self.ach.user_played_hours_game(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_hours_in_one_day_use_that_day(self):
        day = datetime.date(YEAR, 3, 5)
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_day", return_value=[(day, 9 * 3600), (day, None)]):
            await self.ach.user_played_day_time(self.db, USER)
        got = self.awarded()
        self.assertEqual(set(got), {"PLAYED_4_HOURS_DAY", "PLAYED_8_HOURS_DAY"})
        self.assertEqual(got["PLAYED_8_HOURS_DAY"][0], day)

    async def test_early_riser_on_timer_start(self):
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 3, 1, 5, 30))
        self.assertEqual(set(self.awarded()), {"EARLY_RISER"})
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 3, 2, 12, 0))
        self.assertEqual(set(self.awarded()), {"EARLY_RISER"})

    async def test_silent_checks_award_but_pass_silent_on(self):
        await self.ach.user_played_total_days(self.db, USER, self.days(7), silent=True)
        self.assertEqual(self.sent.await_args.args[1], True)
        self.assertEqual(list(self.awarded()), ["PLAYED_7_DAYS"])

    async def test_games_per_day_is_dated_the_earliest_day_that_reached_it(self):
        rows = [(datetime.date(YEAR, 5, 9), 6), (datetime.date(YEAR, 5, 2), 12), (datetime.date(YEAR, 5, 4), 3)]
        with mock.patch.object(ach_module.time_entries, "get_played_games_count_by_day", return_value=rows):
            await self.ach.user_played_games_per_day(self.db, USER)
        got = self.awarded()
        self.assertEqual(got["PLAYED_5_GAMES_DAY"][0], datetime.date(YEAR, 5, 2))
        self.assertEqual(got["PLAYED_10_GAMES_DAY"][0], datetime.date(YEAR, 5, 2))

    async def test_days_already_earned_are_not_awarded_again(self):
        rows = [(datetime.date(YEAR, 5, 2), 12)]
        with mock.patch.object(ach_module.time_entries, "get_played_games_count_by_day", return_value=rows):
            await self.ach.user_played_games_per_day(self.db, USER)
            await self.ach.user_played_games_per_day(self.db, USER)
        self.assertEqual(self.sent.await_count, 2)

    def finished_session(self, start, end):
        self.db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        self.db.add(
            models.GameTimer(
                user_id=1, game_id="g1", start_time=start, end_time=end,
                duration_seconds=int((end - start).total_seconds()), is_active=False,
            )
        )
        self.db.commit()

    async def test_happy_new_year_for_a_session_that_starts_on_the_first(self):
        self.finished_session(datetime.datetime(YEAR, 1, 1, 0, 30), datetime.datetime(YEAR, 1, 1, 1, 0))
        await self.ach.happy_new_year(self.db, USER)
        self.assertEqual(self.awarded()["HAPPY_NEW_YEAR"][0], datetime.date(YEAR, 1, 1))

    async def test_happy_new_year_for_a_session_across_midnight_is_dated_the_first_and_earned_once(self):
        self.finished_session(datetime.datetime(YEAR - 1, 12, 31, 23, 0), datetime.datetime(YEAR, 1, 1, 1, 0))
        await self.ach.happy_new_year(self.db, USER)
        await self.ach.happy_new_year(self.db, USER)
        rows = self.db.query(models.UserAchievement).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].date, datetime.date(YEAR, 1, 1))
        self.assertEqual(rows[0].season, YEAR)
        self.assertEqual(self.sent.await_count, 1)

    async def test_happy_new_year_for_a_session_that_ends_a_day_later(self):
        self.finished_session(datetime.datetime(YEAR - 1, 12, 31, 23, 0), datetime.datetime(YEAR, 1, 2, 3, 0))
        await self.ach.happy_new_year(self.db, USER)
        self.assertEqual(self.awarded()["HAPPY_NEW_YEAR"][0], datetime.date(YEAR, 1, 1))

    async def test_no_happy_new_year_for_sessions_that_do_not_touch_the_first(self):
        self.finished_session(datetime.datetime(YEAR - 1, 12, 31, 20, 0), datetime.datetime(YEAR - 1, 12, 31, 23, 59))
        self.db.add(
            models.GameTimer(
                user_id=1, game_id="g1", start_time=datetime.datetime(YEAR, 1, 2, 10), end_time=datetime.datetime(YEAR, 1, 2, 11),
                duration_seconds=3600, is_active=False,
            )
        )
        self.db.commit()
        await self.ach.happy_new_year(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_teamwork_needs_four_players_with_a_running_timer(self):
        for i in range(2, 6):
            self.db.add(models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1))
            self.db.add(models.GameTimer(user_id=i, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        self.db.commit()
        with mock.patch.object(ach_module.time_entries, "active_timer_user_ids", wraps=ach_module.time_entries.active_timer_user_ids) as ids:
            await self.ach.teamwork(self.db, silent=False)
        ids.assert_called_once()  # one query for everybody, not one per user
        self.assertEqual({k for k in self.awarded()}, {"TEAMWORK"})
        self.assertIn("P2", self.message())

    async def test_three_players_are_not_a_team(self):
        for i in range(2, 5):
            self.db.add(models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1))
            self.db.add(models.GameTimer(user_id=i, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.commit()
        await self.ach.teamwork(self.db, silent=False)
        self.assertEqual(self.awarded(), {})


class QueryEconomyTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_check_costs_one_query_per_group_not_one_per_threshold(self):
        from sqlalchemy import event

        db = make_session()
        ach = Achievements()
        ach.populate_achievements(db)
        queries = []
        event.listen(db.get_bind(), "before_cursor_execute", lambda *a: queries.append(a[2]))
        days = [(datetime.date(YEAR, 1, 1) + datetime.timedelta(days=i), 9 * 3600) for i in range(40)]
        with mock.patch.object(ach_module.utils, "send_message", mock.AsyncMock()),                 mock.patch.object(ach_module.time_entries, "get_played_time_by_day", return_value=days):
            queries.clear()
            await ach.user_streak(db, USER, [])  # nothing reached: no query
            self.assertEqual(queries, [])
            await ach.user_played_day_time(db, USER)
        selects = [q for q in queries if q.lstrip().upper().startswith("SELECT") and "achievements" in q.lower()]
        # one look-up of what is already earned, however many days there are (the rest is the awards)
        self.assertEqual(sum("IN (" in q for q in selects), 1)


if __name__ == "__main__":
    unittest.main()
