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

    async def test_total_time_thresholds(self):
        await self.ach.user_played_total_time(self.db, USER, 250 * 3600)
        self.assertEqual(set(self.awarded()), {"PLAYED_100_HOURS", "PLAYED_200_HOURS"})

    async def test_total_time_without_data_does_nothing(self):
        await self.ach.user_played_total_time(self.db, USER, None)
        self.assertEqual(self.awarded(), {})

    async def test_streaks_use_the_given_date(self):
        await self.ach.user_streak(self.db, USER, 16, datetime.datetime(YEAR, 2, 3, 10, 30))
        got = self.awarded()
        self.assertEqual(set(got), {"STREAK_7_DAYS", "STREAK_15_DAYS"})
        self.assertEqual(got["STREAK_7_DAYS"][0], datetime.date(YEAR, 2, 3))

    async def test_games_played_and_completed(self):
        with mock.patch.object(ach_module.users, "count_played_games", return_value=42), \
                mock.patch.object(ach_module.users, "count_completed_games", return_value=42):
            await self.ach.user_played_total_games(self.db, USER)
            await self.ach.user_completed_total_games(self.db, USER)
        self.assertEqual(
            set(self.awarded()),
            {"PLAYED_10_GAMES", "PLAYED_42_GAMES", "COMPLETED_42_GAMES"},
        )

    async def test_hours_in_a_game_name_the_game(self):
        await self.ach.user_played_hours_game(self.db, USER, "g1", 101 * 3600)
        got = self.awarded()
        self.assertEqual(got["PLAYED_100_HOURS_GAME"][1], "g1")
        self.assertIn("Doom", self.message())

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
            await ach.user_streak(db, USER, 0)  # nothing reached: no query
            self.assertEqual(queries, [])
            await ach.user_played_day_time(db, USER)
        selects = [q for q in queries if q.lstrip().upper().startswith("SELECT") and "achievements" in q.lower()]
        # one look-up of what is already earned, however many days there are (the rest is the awards)
        self.assertEqual(sum("IN (" in q for q in selects), 1)


if __name__ == "__main__":
    unittest.main()
