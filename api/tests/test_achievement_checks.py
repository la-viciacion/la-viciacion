import datetime
import types
import unittest
from unittest import mock

from src.utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from src.crud import achievements as ach_module
from src.crud import time_entries
from src.crud.achievements import Achievements
from src.database import models
from src.utils import seasons
from src.utils.achievements import is_lifetime
from tests.sqlite_db import make_session

USER = types.SimpleNamespace(id=1, name="Ana", telegram_id=111)
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

    def awards_of_everybody(self):
        return [
            (user_id, key, game_id)
            for user_id, key, game_id in self.db.query(models.UserAchievement.user_id, models.Achievement.key, models.UserAchievement.game_id)
            .join(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
            .all()
        ]

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
        self.assertEqual(
            set(got), {"COMPLETED_1_GAME", "COMPLETED_5_GAMES", "COMPLETED_10_GAMES", "COMPLETED_25_GAMES", "COMPLETED_42_GAMES"}
        )
        self.assertEqual(got["COMPLETED_1_GAME"][0], datetime.date(YEAR, 1, 1))
        self.assertEqual(got["COMPLETED_5_GAMES"][0], datetime.date(YEAR, 1, 5))
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

    async def test_500_and_1000_hours_in_a_game_are_earned_each_the_day_it_crossed_them(self):
        rows = [
            (datetime.date(YEAR, 1, 10), "g1", 120 * 3600),
            (datetime.date(YEAR, 3, 1), "g1", 400 * 3600),  # 520 h: the 500
            (datetime.date(YEAR, 6, 1), "g1", 500 * 3600),  # 1020 h: the 1000
        ]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_game_and_day", return_value=rows):
            await self.ach.user_played_hours_game(self.db, USER)
            await self.ach.user_played_hours_game(self.db, USER)
        got = self.awarded()
        self.assertEqual(got["PLAYED_100_HOURS_GAME"], (datetime.date(YEAR, 1, 10), "g1"))
        self.assertEqual(got["PLAYED_500_HOURS_GAME"], (datetime.date(YEAR, 3, 1), "g1"))
        self.assertEqual(got["PLAYED_1000_HOURS_GAME"], (datetime.date(YEAR, 6, 1), "g1"))
        self.assertEqual(self.sent.await_count, 3)

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

    def timers_started_at(self, *starts):
        for start in starts:
            self.db.add(
                models.GameTimer(
                    user_id=1, game_id="g1", start_time=start, end_time=start + datetime.timedelta(hours=1),
                    duration_seconds=3600, is_active=False,
                )
            )
        self.db.commit()

    async def test_early_riser_and_nocturnal_are_dated_the_earliest_session_in_their_hours(self):
        # inserted newest first: the database must not be trusted to return the oldest one first
        self.timers_started_at(
            datetime.datetime(YEAR, 6, 9, 5, 15), datetime.datetime(YEAR, 4, 2, 5, 45), datetime.datetime(YEAR, 5, 1, 5, 0),
            datetime.datetime(YEAR, 8, 9, 3, 0), datetime.datetime(YEAR, 2, 3, 2, 30), datetime.datetime(YEAR, 7, 1, 4, 0),
            datetime.datetime(YEAR, 1, 1, 12, 0),  # neither
        )
        await self.ach.early_riser(self.db, USER, silent=False)
        await self.ach.nocturnal(self.db, USER, silent=False)
        got = self.awarded()
        self.assertEqual(got["EARLY_RISER"][0], datetime.date(YEAR, 4, 2))
        self.assertEqual(got["NOCTURNAL"][0], datetime.date(YEAR, 2, 3))

    async def test_no_session_in_those_hours_awards_nothing(self):
        self.timers_started_at(datetime.datetime(YEAR, 3, 1, 6, 0), datetime.datetime(YEAR, 3, 2, 1, 59))
        await self.ach.early_riser(self.db, USER, silent=False)
        await self.ach.nocturnal(self.db, USER, silent=False)
        self.assertEqual(self.awarded(), {})

    async def test_eight_hours_in_a_game_in_a_day_is_dated_the_first_day_it_happened(self):
        rows = [
            (datetime.date(YEAR, 3, 9), "g1", 9 * 3600),
            (datetime.date(YEAR, 2, 2), "g1", 8 * 3600),
            (datetime.date(YEAR, 1, 5), "g1", 7 * 3600 + 3000),  # not enough
            (datetime.date(YEAR, 1, 6), None, 9 * 3600),
        ]
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_game_and_day", return_value=rows):
            await self.ach.user_played_hours_game_day(self.db, USER)
        self.assertEqual(self.awarded()["PLAYED_8_HOURS_GAME_DAY"], (datetime.date(YEAR, 2, 2), "g1"))
        self.assertEqual(self.sent.await_count, 1)

    async def test_just_in_time_needs_the_time_within_five_percent_of_the_average(self):
        hour = 3600
        for played, avg, expected in (
            (10 * hour, 10 * hour, True),
            (int(10.5 * hour), 10 * hour, True),  # +5 %
            (int(9.5 * hour), 10 * hour, True),  # -5 %
            (int(10.6 * hour), 10 * hour, False),
            (int(9.4 * hour), 10 * hour, False),
            (45 * 60, 3600, False),  # 25 % under: the hour rounding used to let this one in
            (100 * hour + 30 * 60, 100 * hour, True),  # half an hour is nothing on a long game...
            (30 * 60, 2 * hour, False),  # ...and everything on a short one
        ):
            self.db.query(models.UserAchievement).delete()
            self.db.commit()
            await self.ach.just_in_time(self.db, USER, played, avg, "g1")
            self.assertEqual("JUST_IN_TIME" in self.awarded(), expected, (played, avg))

    async def test_just_in_time_without_a_time_or_an_average_does_nothing(self):
        await self.ach.just_in_time(self.db, USER, 0, 3600, "g1")
        await self.ach.just_in_time(self.db, USER, 3600, 0, "g1")
        self.assertEqual(self.awarded(), {})

    def session_of(self, start, minutes, game="g1"):
        self.db.add(
            models.GameTimer(
                user_id=1, game_id=game, start_time=start, end_time=start + datetime.timedelta(minutes=minutes),
                duration_seconds=minutes * 60, is_active=False,
            )
        )
        self.db.commit()

    async def test_hours_add_up_whatever_the_length_of_each_session(self):
        self.session_of(datetime.datetime(YEAR, 3, 1, 8, 0), 180)
        for n in range(20):  # three more hours, in sessions of nine minutes
            self.session_of(datetime.datetime(YEAR, 3, 1, 12, 0) + datetime.timedelta(minutes=10 * n), 9)
        await self.ach.user_played_day_time(self.db, USER)
        self.assertEqual(set(self.awarded()), {"PLAYED_4_HOURS_DAY"})

    async def test_trying_games_for_less_than_ten_minutes_is_not_trying_them(self):
        for n in range(5):
            self.session_of(datetime.datetime(YEAR, 3, 1, 8 + n), 3, game=f"g{n}")
        await self.ach.user_played_games_per_day(self.db, USER)
        self.assertEqual(self.awarded(), {})
        for n in range(5):
            self.session_of(datetime.datetime(YEAR, 3, 2, 8 + n), 10, game=f"g{n}")
        await self.ach.user_played_games_per_day(self.db, USER)
        self.assertEqual(set(self.awarded()), {"PLAYED_5_GAMES_DAY"})

    async def test_the_new_year_does_not_look_at_the_length_of_the_session(self):
        self.session_of(datetime.datetime(YEAR, 1, 1, 0, 30), 1)
        await self.ach.happy_new_year(self.db, USER)
        self.assertEqual(set(self.awarded()), {"HAPPY_NEW_YEAR"})

    async def test_starting_a_timer_on_the_first_of_january_earns_the_new_year_at_once(self):
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 1, 2, 0, 30))
        self.assertEqual(self.awarded(), {})
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 1, 1, 0, 30))
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 1, 1, 9, 0))
        got = self.awarded()
        self.assertEqual(set(got), {"HAPPY_NEW_YEAR"})
        self.assertEqual(got["HAPPY_NEW_YEAR"][0], datetime.date(YEAR, 1, 1))
        self.assertEqual(self.sent.await_count, 1)

    async def test_early_riser_does_not_look_at_the_length_because_it_fires_when_the_timer_starts(self):
        self.session_of(datetime.datetime(YEAR, 3, 1, 5, 30), 1)
        await self.ach.early_riser(self.db, USER, silent=False)
        self.assertEqual(set(self.awarded()), {"EARLY_RISER"})

    async def test_opened_by_mistake_comes_from_a_timer_that_stopped_within_five_minutes(self):
        start = datetime.datetime(YEAR, 3, 1, 8)
        await self.ach.opened_by_mistake(self.db, USER, "g1", start, 5 * 60)
        self.assertEqual(self.awarded()["PLAYED_LESS_5_MIN_SESSION"], (datetime.date(YEAR, 3, 1), "g1"))
        self.assertIn("Doom", self.message())

    async def test_opened_by_mistake_needs_some_time_and_not_too_much(self):
        for seconds in (None, 0, 5 * 60 + 1):
            await self.ach.opened_by_mistake(self.db, USER, "g1", datetime.datetime(YEAR, 3, 1, 8), seconds)
        self.assertEqual(self.awarded(), {})

    async def test_the_sessions_of_the_database_never_earn_it(self):
        self.session_of(datetime.datetime(YEAR, 3, 1, 8), 3)  # a manual session looks the same as a timer
        await self.ach.user_session_time(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_the_prodigal_son_needs_thirty_days_without_playing(self):
        await self.ach.prodigal_son(self.db, USER, [datetime.date(YEAR, 1, 1), datetime.date(YEAR, 1, 31)])  # 29 days without
        self.assertEqual(self.awarded(), {})
        await self.ach.prodigal_son(self.db, USER, [datetime.date(YEAR, 1, 1), datetime.date(YEAR, 2, 1), datetime.date(YEAR, 6, 1)])
        got = self.awarded()
        self.assertEqual(set(got), {"PRODIGAL_SON"})
        self.assertEqual(got["PRODIGAL_SON"][0], datetime.date(YEAR, 2, 1))  # the first time they came back
        self.assertEqual(self.sent.await_count, 1)

    async def test_a_work_week_is_forty_hours_between_monday_and_sunday(self):
        march_1 = datetime.date(YEAR, 3, 1)
        monday = march_1 - datetime.timedelta(days=march_1.weekday())
        for offset in (6, 7, 8, 9, 10):  # Sunday of the week before and Monday to Thursday: 5 days, but two weeks
            day = monday + datetime.timedelta(days=offset - 7)
            self.session_of(datetime.datetime.combine(day, datetime.time(9)), 8 * 60)
        await self.ach.work_week(self.db, USER)
        self.assertEqual(self.awarded(), {})  # 8 h on the Sunday and 32 h in the week itself
        friday = monday + datetime.timedelta(days=4)
        self.session_of(datetime.datetime.combine(friday, datetime.time(9)), 8 * 60)
        await self.ach.work_week(self.db, USER)
        got = self.awarded()
        self.assertEqual(set(got), {"WORK_WEEK"})
        self.assertEqual(got["WORK_WEEK"][0], friday)

    async def test_saved_by_the_bell_needs_a_session_running_at_midnight(self):
        self.session_of(datetime.datetime(YEAR - 1, 12, 31, 22, 0), 60)  # ends at 23:00
        self.session_of(datetime.datetime(YEAR - 1, 12, 31, 23, 0), 60)  # ends exactly at midnight
        self.session_of(datetime.datetime(YEAR, 1, 1, 0, 0), 30)  # starts at midnight
        await self.ach.saved_by_the_bell(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.session_of(datetime.datetime(YEAR - 1, 12, 31, 23, 30), 60)  # 23:30 to 00:30
        await self.ach.saved_by_the_bell(self.db, USER)
        got = self.awarded()
        self.assertEqual(got["SAVED_BY_THE_BELL"], (datetime.date(YEAR, 1, 1), "g1"))  # of the new season, naming the game
        self.assertIn("Doom", self.message())

    async def test_a_game_completed_in_one_day_needs_all_its_sessions_on_that_day(self):
        self.library_entry("g1", datetime.date(YEAR, 3, 1), completed=datetime.date(YEAR, 3, 4))
        self.db.commit()
        self.session_of(datetime.datetime(YEAR, 3, 1, 20), 120)
        self.session_of(datetime.datetime(YEAR, 3, 1, 23), 30)
        await self.ach.completed_in_a_day(self.db, USER)
        self.assertEqual(self.awarded()["COMPLETED_IN_A_DAY"], (datetime.date(YEAR, 3, 4), "g1"))  # dated the completion

    async def test_a_game_played_on_two_days_is_not_completed_in_one(self):
        self.library_entry("g1", datetime.date(YEAR, 3, 1), completed=datetime.date(YEAR, 3, 4))
        self.db.commit()
        self.session_of(datetime.datetime(YEAR, 3, 1, 20), 120)
        self.session_of(datetime.datetime(YEAR, 3, 2, 20), 120)
        await self.ach.completed_in_a_day(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_playing_a_game_the_day_it_came_out(self):
        self.db.query(models.Game).filter_by(id="g1").update({"release_date": datetime.date(YEAR, 3, 5)})
        self.db.commit()
        self.session_of(datetime.datetime(YEAR, 3, 6, 20), 30)  # a day late
        await self.ach.release_day(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.session_of(datetime.datetime(YEAR, 3, 5, 20), 30)
        await self.ach.release_day(self.db, USER)
        self.assertEqual(self.awarded()["RELEASE_DAY"], (datetime.date(YEAR, 3, 5), "g1"))

    async def test_a_timer_started_on_the_release_day_earns_it_at_once(self):
        self.db.query(models.Game).filter_by(id="g1").update({"release_date": datetime.date(YEAR, 3, 5)})
        self.db.commit()
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 3, 4, 20), "g1")
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 3, 5, 20), None)
        self.assertEqual(self.awarded(), {})
        await self.ach.timer_started(self.db, USER, datetime.datetime(YEAR, 3, 5, 20), "g1")
        self.assertEqual(self.awarded()["RELEASE_DAY"], (datetime.date(YEAR, 3, 5), "g1"))

    async def test_three_players_on_the_same_game_are_all_together(self):
        for i in (2, 3):
            self.db.add(models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1))
            self.db.add(models.GameTimer(user_id=i, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.commit()
        await self.ach.all_together(self.db, "g1")
        self.assertEqual(self.awarded(), {})  # two are not enough
        self.db.add(models.User(id=4, name="P4", username="p4", is_active=1))
        self.db.add(models.GameTimer(user_id=4, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.add(models.GameTimer(user_id=5, game_id="g2", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))  # another game
        self.db.commit()
        await self.ach.all_together(self.db, "g1")
        await self.ach.all_together(self.db, "g1")
        self.assertEqual(self.sent.await_count, 1)
        self.assertEqual({user for user, key, _ in self.awards_of_everybody() if key == "ALL_TOGETHER"}, {2, 3, 4})
        self.assertIn("P2, P3 y P4", self.message())
        self.assertIn("Doom", self.message())

    def switch_off(self, *keys):
        self.db.query(models.Achievement).filter(models.Achievement.key.in_(keys)).update({"active": False}, synchronize_session=False)
        self.db.commit()

    async def test_a_switched_off_achievement_is_not_earned_nor_announced_and_the_rest_still_are(self):
        self.switch_off("PLAYED_7_DAYS", "STREAK_7_DAYS", "TEAMWORK")
        await self.ach.user_played_total_days(self.db, USER, self.days(15))
        await self.ach.user_streak(self.db, USER, self.days(15))
        self.assertEqual(set(self.awarded()), {"PLAYED_15_DAYS", "STREAK_15_DAYS"})
        self.assertEqual(self.sent.await_count, 2)

    async def test_switching_it_on_makes_it_earnable_again(self):
        self.switch_off("PLAYED_7_DAYS")
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(self.awarded(), {})
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"active": True})
        self.db.commit()
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(set(self.awarded()), {"PLAYED_7_DAYS"})

    async def test_what_a_switched_off_achievement_already_has_is_kept(self):
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.switch_off("PLAYED_7_DAYS")
        self.assertEqual(set(self.awarded()), {"PLAYED_7_DAYS"})

    async def test_teamwork_and_the_games_at_once_ignore_it_when_it_is_off(self):
        self.switch_off("ALL_TOGETHER")
        for i in (2, 3, 4):
            self.db.add(models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1))
            self.db.add(models.GameTimer(user_id=i, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.commit()
        await self.ach.all_together(self.db, "g1")
        self.assertEqual(self.awarded(), {})
        self.sent.assert_not_awaited()

    async def test_a_check_that_only_works_out_what_is_deserved_skips_it_too(self):
        self.switch_off("PLAYED_7_DAYS")
        collected = []
        checks = Achievements(season=YEAR, collected=collected)
        await checks.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(collected, [])

    async def test_the_new_achievements_of_an_installation_that_has_some_start_switched_off(self):
        from tests.sqlite_db import make_session as fresh

        db = fresh()
        Achievements().populate_achievements(db)  # nothing there yet: everything is on
        self.assertEqual(db.query(models.Achievement).filter(models.Achievement.active == False).count(), 0)  # noqa: E712
        db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").delete()
        db.commit()
        Achievements().populate_achievements(db)  # one is added to an installation that has the rest
        got = {a.key: a.active for a in db.query(models.Achievement)}
        self.assertFalse(got["PLAYED_7_DAYS"])
        self.assertTrue(got["PLAYED_15_DAYS"])

    def make_secret(self, *keys):
        self.db.query(models.Achievement).filter(models.Achievement.key.in_(keys)).update({"secret": True}, synchronize_session=False)
        self.db.commit()
        private = mock.AsyncMock()
        patcher = mock.patch.object(ach_module.utils, "send_message_to_user", private)
        patcher.start()
        self.addCleanup(patcher.stop)
        return private

    async def test_a_secret_one_is_told_to_the_group_without_saying_which_and_to_the_player_in_full(self):
        private = self.make_secret("PLAYED_7_DAYS")
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(set(self.awarded()), {"PLAYED_7_DAYS"})  # it is earned all the same
        group = self.message()
        self.assertIn("Ana", group)
        self.assertIn("ha desbloqueado un logro oculto", group)
        self.assertNotIn("7 días", group)  # nothing that gives it away
        self.assertEqual(self.sent.await_args.kwargs, {})  # and no picture
        private.assert_awaited_once()
        telegram_id, text = private.await_args.args
        self.assertEqual((telegram_id, private.await_args.kwargs), (111, {"user_id": 1}))
        self.assertIn("7 días jugados", text)  # the player gets the whole notice

    async def test_what_is_not_secret_is_announced_as_ever_and_nobody_is_told_privately(self):
        private = self.make_secret("PLAYED_15_DAYS")
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertIn("7 días jugados", self.message())
        private.assert_not_awaited()

    async def test_a_silent_check_tells_nobody_not_even_the_player(self):
        private = self.make_secret("PLAYED_7_DAYS")
        await self.ach.user_played_total_days(self.db, USER, self.days(7), silent=True)
        self.assertEqual(self.sent.await_args.args[1], True)
        private.assert_not_awaited()

    async def test_several_players_that_unlock_a_secret_are_named_together_and_each_is_told_privately(self):
        private = self.make_secret("TEAMWORK", "ALL_TOGETHER")
        for i in range(2, 6):
            self.db.add(models.User(id=i, name=f"P{i}", username=f"p{i}", is_active=1))
            self.db.add(models.GameTimer(user_id=i, game_id="g1", start_time=datetime.datetime(YEAR, 3, 1, 10), is_active=True))
        self.db.commit()
        await self.ach.teamwork(self.db, silent=False)
        self.assertIn("P2, P3, P4 y P5 han desbloqueado un logro oculto", self.message(0))
        self.assertEqual(private.await_count, 4)
        await self.ach.all_together(self.db, "g1")
        self.assertIn("P2, P3, P4 y P5 han desbloqueado un logro oculto", self.message(1))
        self.assertEqual(private.await_count, 8)

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


class LifetimeTests(unittest.IsolatedAsyncioTestCase):
    """The achievements whose key ends in _LIFETIME: the whole history of a player, earned once."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.Game(id="g1", name="Doom"), models.Game(id="g2", name="Quake")])
        self.db.commit()
        Achievements().populate_achievements(self.db)
        self.sent = mock.AsyncMock()
        patcher = mock.patch.object(ach_module.utils, "send_message", self.sent)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.view = Achievements(season=seasons.ALL)

    def awarded(self):
        rows = (
            self.db.query(models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id)
            .join(models.UserAchievement, models.UserAchievement.achievement_id == models.Achievement.id)
            .all()
        )
        return {key: (date, game_id) for key, date, game_id in rows}

    def play(self, start, hours=1, game="g1"):
        self.db.add(models.GameTimer(
            user_id=1, game_id=game, start_time=start, end_time=start + datetime.timedelta(hours=hours),
            duration_seconds=int(hours * 3600), is_active=False,
        ))
        self.db.commit()

    def switch_off_lifetime(self):
        self.db.query(models.Achievement).filter(models.Achievement.key.like("%\\_LIFETIME", escape="\\")).update(
            {"active": False}, synchronize_session=False
        )
        self.db.commit()

    def test_the_key_is_the_rule_and_every_one_of_them_has_its_table(self):
        tables = (
            ach_module.LIFETIME_TOTAL_HOURS, ach_module.LIFETIME_TOTAL_DAYS, ach_module.LIFETIME_PLAYED_GAMES,
            ach_module.LIFETIME_COMPLETED_GAMES, ach_module.LIFETIME_HOURS_IN_A_GAME,
        )
        in_tables = {ach.name for table in tables for ach, _ in table}
        by_name = {ach.name for ach in ach_module.AchievementsElems if is_lifetime(ach.name)}
        self.assertEqual(in_tables, by_name)  # a typo in the suffix would turn one into a seasonal one without a word
        self.assertEqual(len(by_name), 20)
        for table in tables:
            self.assertTrue(all(is_lifetime(ach.name) for ach, _ in table))
        for table in (ach_module.TOTAL_HOURS, ach_module.TOTAL_DAYS, ach_module.PLAYED_GAMES, ach_module.COMPLETED_GAMES, ach_module.HOURS_IN_A_GAME):
            self.assertFalse(any(is_lifetime(ach.name) for ach, _ in table))

    async def test_1000_hours_in_a_game_add_up_over_the_seasons_and_name_the_game(self):
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=600)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=500)  # 1100: it crosses on this day
        self.play(datetime.datetime(YEAR, 3, 2, 10), hours=900, game="g2")  # another game does not count
        await self.view.user_played_hours_game(self.db, USER)
        await self.view.user_played_hours_game(self.db, USER)  # and it is earned once
        got = self.awarded()
        self.assertEqual(got, {"PLAYED_1000_HOURS_GAME_LIFETIME": (datetime.date(YEAR, 3, 1), "g1")})
        self.assertEqual(self.sent.await_count, 1)
        self.assertIn("Doom", self.sent.await_args.args[0])

    async def test_neither_season_alone_is_enough_but_a_seasonal_check_is_not_this_one(self):
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=550)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=550)
        await Achievements().user_played_hours_game(self.db, USER)  # the season: only 550 h
        self.assertEqual(set(self.awarded()), {"PLAYED_100_HOURS_GAME", "PLAYED_500_HOURS_GAME"})  # and none of the lifetime ones

    async def test_a_lifetime_one_already_earned_in_another_season_is_not_earned_again(self):
        key_id = self.db.query(models.Achievement.id).filter_by(key="PLAYED_1000_HOURS_GAME_LIFETIME").scalar()
        self.db.add(models.UserAchievement(user_id=1, achievement_id=key_id, date=datetime.date(YEAR - 1, 6, 1), game_id="g1"))
        self.db.commit()
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=1100)
        await self.view.user_played_hours_game(self.db, USER)
        self.assertEqual(self.db.query(models.UserAchievement).count(), 1)
        self.sent.assert_not_awaited()

    async def test_total_hours_add_up_over_the_seasons(self):
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=400)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=150)
        await self.view.user_played_total_time(self.db, USER)
        self.assertEqual(self.awarded(), {"PLAYED_500_HOURS_LIFETIME": (datetime.date(YEAR, 3, 1), None)})

    async def test_played_days_add_up_over_the_seasons_and_are_dated_the_day_that_reached_them(self):
        for day in range(60):
            self.play(datetime.datetime(YEAR - 1, 1, 1, 10) + datetime.timedelta(days=day), hours=0.5)
        for day in range(50):
            self.play(datetime.datetime(YEAR, 1, 1, 10) + datetime.timedelta(days=day), hours=0.5)
        days = time_entries.get_played_days(self.db, 1, season=seasons.ALL)
        await self.view.user_played_total_days(self.db, USER, days)
        got = self.awarded()
        self.assertEqual(set(got), {"PLAYED_100_DAYS_LIFETIME"})
        self.assertEqual(got["PLAYED_100_DAYS_LIFETIME"][0], datetime.date(YEAR, 1, 1) + datetime.timedelta(days=39))  # 60 + 40

    async def test_games_played_count_each_game_once_whatever_the_seasons(self):
        for n in range(50):
            self.db.add(models.UserGame(user_id=1, game_id=f"a{n}", started_date=datetime.date(YEAR - 1, 3, 1), platform=None, completed=0))
        for n in range(49):
            self.db.add(models.UserGame(user_id=1, game_id=f"b{n}", started_date=datetime.date(YEAR, 3, 1), platform=None, completed=0))
        self.db.add(models.UserGame(user_id=1, game_id="a0", started_date=datetime.date(YEAR, 4, 1), platform=None, completed=0))  # again
        self.db.commit()
        await self.view.user_played_total_games(self.db, USER)
        self.assertEqual(self.awarded(), {})  # 99 different ones
        self.db.add(models.UserGame(user_id=1, game_id="b49", started_date=datetime.date(YEAR, 5, 1), platform=None, completed=0))
        self.db.commit()
        await self.view.user_played_total_games(self.db, USER)
        self.assertEqual(self.awarded(), {"PLAYED_100_GAMES_LIFETIME": (datetime.date(YEAR, 5, 1), None)})

    async def test_games_completed_count_each_game_once_whatever_the_seasons(self):
        for n in range(50):
            self.db.add(models.UserGame(user_id=1, game_id=f"a{n}", started_date=datetime.date(YEAR - 1, 3, 1), platform=None,
                                        completed=1, completed_date=datetime.date(YEAR - 1, 3, 2)))
        for n in range(49):
            self.db.add(models.UserGame(user_id=1, game_id=f"b{n}", started_date=datetime.date(YEAR, 3, 1), platform=None,
                                        completed=1, completed_date=datetime.date(YEAR, 3, 2)))
        self.db.add(models.UserGame(user_id=1, game_id="a0", started_date=datetime.date(YEAR, 4, 1), platform=None,
                                    completed=1, completed_date=datetime.date(YEAR, 4, 2)))  # the same game completed again
        self.db.commit()
        await self.view.user_completed_total_games(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.db.add(models.UserGame(user_id=1, game_id="b49", started_date=datetime.date(YEAR, 5, 1), platform=None,
                                    completed=1, completed_date=datetime.date(YEAR, 5, 2)))
        self.db.commit()
        await self.view.user_completed_total_games(self.db, USER)
        self.assertEqual(self.awarded(), {"COMPLETED_100_GAMES_LIFETIME": (datetime.date(YEAR, 5, 2), None)})

    async def test_while_none_is_switched_on_the_checks_over_the_whole_history_cost_nothing(self):
        self.switch_off_lifetime()
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_day") as by_day, \
                mock.patch.object(ach_module.users, "played_game_dates") as games:
            await self.view.user_played_total_time(self.db, USER)
            await self.view.user_played_total_games(self.db, USER)
        by_day.assert_not_called()
        games.assert_not_called()

    async def test_the_seasonal_checks_never_earn_a_lifetime_one(self):
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=600)
        await Achievements().user_played_total_time(self.db, USER)
        self.assertEqual(set(self.awarded()), {"PLAYED_100_HOURS", "PLAYED_200_HOURS", "PLAYED_500_HOURS"})

    async def test_the_orchestration_runs_the_lifetime_checks_too(self):
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=400)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=150)
        await actions.check_user_lifetime(self.db, USER, checks=self.view)
        self.assertIn("PLAYED_500_HOURS_LIFETIME", self.awarded())


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
