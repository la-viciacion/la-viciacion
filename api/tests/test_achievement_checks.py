import datetime
import types
import unittest
from unittest import mock

from src.utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from src.crud import achievements as ach_module
from src.crud import time_entries
from src.crud.achievements import Achievements
from src.database import models
from src.utils import astronomy, seasons, weather
from src.utils.achievements import first_season, is_lifetime
from tests.sqlite_db import make_session
from tests import clock

USER = types.SimpleNamespace(id=1, name="Ana", telegram_id=111)
YEAR = clock.YEAR


class AchievementCheckTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g1", name="Doom", slug="doom"))
        self.db.commit()
        self.ach = Achievements()
        self.ach.populate_achievements(self.db)
        self.db.query(models.Achievement).update({"valid_from_season": 2023, "special": 0, "secret": False})  # some are special or secret: not what is tested here
        self.db.commit()
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

    def returned_game(self, avg_time, before_minutes, completed=datetime.date(YEAR, 6, 12)):
        """A game played `before_minutes` in January, left alone until June and finished then."""
        self.db.query(models.Game).filter_by(id="g1").update({"avg_time": avg_time})
        self.library_entry("g1", datetime.date(YEAR, 1, 10), completed=completed)
        self.db.commit()
        self.session_of(datetime.datetime(YEAR, 1, 10, 20), before_minutes)
        self.session_of(datetime.datetime(YEAR, 6, 10, 20), 120)

    async def test_a_game_finished_after_ninety_days_alone_is_a_rescue(self):
        self.returned_game(avg_time=100 * 3600, before_minutes=60)  # 1 % of the game: not a finishing touch
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(self.awarded(), {"RESCUE": (datetime.date(YEAR, 6, 12), "g1")})  # dated the completion, naming the game
        self.assertIn("Doom", self.message())

    async def test_coming_back_when_it_was_past_eighty_percent_is_also_a_finishing_touch(self):
        self.returned_game(avg_time=10 * 3600, before_minutes=8 * 60)  # exactly 80 %
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(set(self.awarded()), {"RESCUE", "FINISHING_TOUCH"})
        self.assertEqual(self.sent.await_count, 2)

    async def test_a_game_with_no_average_time_is_a_rescue_never_a_finishing_touch(self):
        self.returned_game(avg_time=0, before_minutes=600)
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(set(self.awarded()), {"RESCUE"})

    async def test_a_game_left_alone_for_less_than_ninety_days_is_neither(self):
        self.library_entry("g1", datetime.date(YEAR, 1, 10), completed=datetime.date(YEAR, 4, 12))
        self.db.commit()
        self.session_of(datetime.datetime(YEAR, 1, 10, 20), 120)
        self.session_of(datetime.datetime(YEAR, 4, 10, 20), 120)  # 89 days without a session
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_it_has_to_be_finished_after_coming_back(self):
        self.returned_game(avg_time=3600, before_minutes=60, completed=datetime.date(YEAR, 3, 1))  # completed before the comeback
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_the_time_alone_counts_across_the_year_change(self):
        self.library_entry("g1", datetime.date(YEAR - 1, 9, 1))
        self.library_entry("g1", datetime.date(YEAR, 2, 1), completed=datetime.date(YEAR, 2, 3))
        self.db.commit()
        self.session_of(datetime.datetime(YEAR - 1, 9, 1, 20), 120)
        self.session_of(datetime.datetime(YEAR, 2, 1, 20), 120)  # 153 days later, in the next season
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(set(self.awarded()), {"RESCUE"})

    async def test_each_is_earned_once_and_nothing_is_checked_again_when_both_are_had(self):
        self.returned_game(avg_time=10 * 3600, before_minutes=9 * 60)
        await self.ach.rescued_games(self.db, USER)
        await self.ach.rescued_games(self.db, USER)
        self.assertEqual(sorted(self.awarded()), ["FINISHING_TOUCH", "RESCUE"])
        self.assertEqual(self.sent.await_count, 2)

    async def test_the_pure_rule_reads_the_gap_in_days_without_a_session(self):
        def sessions(*days):
            return [(datetime.datetime(YEAR, 1, 1) + datetime.timedelta(days=d), datetime.datetime(YEAR, 1, 1, 1) + datetime.timedelta(days=d), 3600) for d in days]
        self.assertEqual(ach_module.rescue_of(sessions(0, 91), 3600), (True, True))  # 90 days between them
        self.assertEqual(ach_module.rescue_of(sessions(0, 90), 3600), (False, False))  # 89
        self.assertEqual(ach_module.rescue_of(sessions(0), 3600), (False, False))
        self.assertEqual(ach_module.rescue_of([], 3600), (False, False))
        self.assertEqual(ach_module.rescue_of(sessions(0, 200), 100 * 3600), (True, False))  # 1 hour of 100

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

    async def test_a_new_achievement_starts_active_and_valid_from_the_season_its_definition_says(self):
        from tests.sqlite_db import make_session as fresh

        db = fresh()
        Achievements().populate_achievements(db)
        got = {a.key: (a.active, a.valid_from_season) for a in db.query(models.Achievement)}
        self.assertEqual(got["PLAYED_7_DAYS"], (True, 2023))  # from the first season of the app
        self.assertEqual(got["PLAYED_1000_HOURS_GAME_LIFETIME"], (True, 2023))  # the later ones are retroactive too
        self.assertEqual(got["COMPLETED_1_GAME"], (True, 2023))
        db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").delete()
        db.commit()
        Achievements().populate_achievements(db)  # one is added to an installation that has the rest
        again = {a.key: (a.active, a.valid_from_season) for a in db.query(models.Achievement)}
        self.assertEqual(again["PLAYED_7_DAYS"], (True, 2023))

    async def test_an_achievement_that_is_not_valid_yet_is_not_earned_until_its_season(self):
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"valid_from_season": YEAR + 1})
        self.db.commit()
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(self.awarded(), {})
        self.sent.assert_not_awaited()
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"valid_from_season": YEAR})
        self.db.commit()
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual(set(self.awarded()), {"PLAYED_7_DAYS"})

    async def test_what_it_would_earn_in_a_season_before_its_own_is_not_worked_out(self):
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"valid_from_season": YEAR})
        self.db.commit()
        before = [datetime.date(YEAR - 1, 3, day) for day in range(1, 8)]
        collected = []
        await Achievements(season=YEAR - 1, collected=collected).user_played_total_days(self.db, USER, before)
        self.assertEqual(collected, [])
        await Achievements(season=YEAR, collected=collected).user_played_total_days(self.db, USER, self.days(7))
        self.assertEqual([award.key for award in collected], ["PLAYED_7_DAYS"])

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

    async def test_a_special_one_is_secret_even_if_it_is_not_marked_so_and_says_its_level_to_the_player(self):
        private = self.make_secret()
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"special": 3})
        self.db.commit()
        self.assertFalse(self.db.query(models.Achievement.secret).filter_by(key="PLAYED_7_DAYS").scalar())  # the mark is not set
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        group = self.message()
        self.assertIn("ha desbloqueado un logro oculto", group)  # the group is told nothing else about it...
        self.assertTrue(group.startswith("Logro especial de nivel 3\n"))  # ...but its level, the interesting part
        self.assertNotIn("7 días", group)
        self.assertIn("Logro especial de nivel 3", private.await_args.args[1])

    async def test_a_special_and_secret_one_is_anonymous_to_the_group_and_special_to_the_player(self):
        private = self.make_secret("PLAYED_7_DAYS")
        self.db.query(models.Achievement).filter_by(key="PLAYED_7_DAYS").update({"special": 1})
        self.db.commit()
        await self.ach.user_played_total_days(self.db, USER, self.days(7))
        self.assertIn("ha desbloqueado un logro oculto", self.message())
        self.assertTrue(self.message().startswith("Logro especial de nivel 1\n"))  # the level is told to the group too
        self.assertIn("Logro especial de nivel 1", private.await_args.args[1])
        self.assertNotIn("7 días", self.message())

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
        self.assertIn("*P2, P3, P4 y P5* han desbloqueado un logro oculto", self.message(0))
        self.assertEqual(private.await_count, 4)
        await self.ach.all_together(self.db, "g1")
        self.assertIn("*P2, P3, P4 y P5* han desbloqueado un logro oculto", self.message(1))
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
        self.db.query(models.Achievement).update({"valid_from_season": 2023, "special": 0, "secret": False})  # some are special or secret: not what is tested here
        self.db.commit()
        self.sent = mock.AsyncMock()
        patcher = mock.patch.object(ach_module.utils, "send_message", self.sent)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.view = Achievements(season=seasons.ALL, since=2023)

    def valid_from(self, key, season):
        self.db.query(models.Achievement).filter_by(key=key).update({"valid_from_season": season})
        self.db.commit()

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
        outside_world = {ach.name for ach in ach_module.EXTERNAL_LIFETIME}  # about when and what, not how much: no tables
        by_name = {ach.name for ach in ach_module.AchievementsElems if is_lifetime(ach.name)}
        self.assertEqual(in_tables | outside_world, by_name)  # a typo in the suffix would turn one into a seasonal one without a word
        self.assertTrue(in_tables.isdisjoint(outside_world))
        self.assertEqual((len(in_tables), len(outside_world)), (20, 15))
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
        self.assertEqual(Achievements().lifetime_views(self.db), [])
        with mock.patch.object(ach_module.time_entries, "get_played_time_by_day") as by_day, \
                mock.patch.object(ach_module.users, "played_game_dates") as games:
            await actions.check_user_lifetime(self.db, USER)
        by_day.assert_not_called()
        games.assert_not_called()

    async def test_only_what_was_done_from_its_season_on_counts(self):
        self.valid_from("PLAYED_1000_HOURS_GAME_LIFETIME", YEAR)
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=600)  # before its season: it does not count
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=500)
        await actions.check_user_lifetime(self.db, USER)
        self.assertNotIn("PLAYED_1000_HOURS_GAME_LIFETIME", self.awarded())  # 500 h from 2026, not 1100
        self.valid_from("PLAYED_1000_HOURS_GAME_LIFETIME", YEAR - 1)
        await actions.check_user_lifetime(self.db, USER)
        self.assertEqual(self.awarded()["PLAYED_1000_HOURS_GAME_LIFETIME"], (datetime.date(YEAR, 3, 1), "g1"))

    async def test_what_is_played_and_completed_before_its_season_does_not_count_either(self):
        self.valid_from("PLAYED_100_GAMES_LIFETIME", YEAR)
        self.valid_from("COMPLETED_100_GAMES_LIFETIME", YEAR)
        for n in range(60):
            self.db.add(models.UserGame(user_id=1, game_id=f"a{n}", started_date=datetime.date(YEAR - 1, 3, 1), platform=None,
                                        completed=1, completed_date=datetime.date(YEAR - 1, 3, 2)))
        for n in range(60):
            self.db.add(models.UserGame(user_id=1, game_id=f"b{n}", started_date=datetime.date(YEAR, 3, 1), platform=None,
                                        completed=1, completed_date=datetime.date(YEAR, 3, 2)))
        self.db.commit()
        await actions.check_user_lifetime(self.db, USER)
        self.assertEqual(self.awarded(), {})  # 120 games in all, 60 from the season

    async def test_one_that_is_not_valid_yet_is_not_worked_out(self):
        self.valid_from("PLAYED_1000_HOURS_GAME_LIFETIME", YEAR + 1)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=1100)
        await actions.check_user_lifetime(self.db, USER)
        self.assertNotIn("PLAYED_1000_HOURS_GAME_LIFETIME", self.awarded())  # the others it earns on the way are valid

    async def test_there_is_one_view_for_each_season_the_ones_that_can_be_earned_count_from(self):
        self.valid_from("PLAYED_100_DAYS_LIFETIME", YEAR - 1)
        self.valid_from("PLAYED_500_HOURS_LIFETIME", YEAR)
        self.valid_from("PLAYED_1000_HOURS_LIFETIME", YEAR + 1)  # not yet: no view for it
        views = Achievements().lifetime_views(self.db)
        self.assertEqual([view.since for view in views], [2023, YEAR - 1, YEAR])
        self.assertTrue(all(view.lifetime for view in views))

    async def test_the_seasonal_checks_never_earn_a_lifetime_one(self):
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=600)
        await Achievements().user_played_total_time(self.db, USER)
        self.assertEqual(set(self.awarded()), {"PLAYED_100_HOURS", "PLAYED_200_HOURS", "PLAYED_500_HOURS"})

    async def test_the_orchestration_runs_the_lifetime_checks_too(self):
        self.play(datetime.datetime(YEAR - 1, 3, 1, 10), hours=400)
        self.play(datetime.datetime(YEAR, 3, 1, 10), hours=150)
        await actions.check_user_lifetime(self.db, USER)
        self.assertIn("PLAYED_500_HOURS_LIFETIME", self.awarded())


# the ones whose message names a game: the player and the game
WITH_A_GAME = {"HORROR_FOG_LIFETIME", "STAR_WARS_DAY_LIFETIME", "MARIO_DAY_LIFETIME", "ARCHAEOLOGIST_LIFETIME", "BIRTH_YEAR_GAME_LIFETIME"}


def utc(jde):
    """The sky in UTC, whatever the time zone of the machine that runs the test."""
    return datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=(jde - astronomy.UNIX_EPOCH_JD) * 86400.0 - astronomy.DELTA_T)


class OutsideWorldTests(unittest.IsolatedAsyncioTestCase):
    """The achievements about the weather, the calendar, the sky and the age of a game (all with no season limit)."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Game(id="g1", name="Doom", slug="doom", release_date=datetime.date(1993, 12, 10), tags="Singleplayer"),
            models.Game(id="sw", name="STAR WARS Jedi: Fallen Order", slug="sw", release_date=datetime.date(2019, 11, 15)),
            models.Game(id="mario", name="Super Mario Odyssey", slug="mario", release_date=datetime.date(2017, 10, 27)),
            models.Game(id="sh", name="Silent Hill 2", slug="sh", release_date=datetime.date(2001, 9, 24), tags="Horror,Singleplayer"),
            models.Game(id="new", name="Hades II", slug="new", release_date=datetime.date(2025, 9, 25)),
        ])
        self.db.commit()
        Achievements().populate_achievements(self.db)
        self.db.query(models.Achievement).update({"valid_from_season": 2023, "special": 0, "secret": False})
        self.db.commit()
        self.sent = mock.AsyncMock()
        for patcher in (
            mock.patch.object(ach_module.utils, "send_message", self.sent),
            mock.patch.object(astronomy, "_local", utc),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.clear_sky()
        self.addCleanup(self.clear_sky)
        self.view = Achievements(season=seasons.ALL, since=2023)

    def clear_sky(self):
        for cached in (astronomy.full_moons, astronomy._eclipses_of, astronomy._solar_eclipse_days_at, astronomy._lunar_eclipse_nights_at, astronomy.sun_events):
            cached.cache_clear()

    def play(self, start, hours=1.0, game="g1", minutes=None):
        length = datetime.timedelta(minutes=minutes) if minutes is not None else datetime.timedelta(hours=hours)
        self.db.add(models.GameTimer(
            user_id=1, game_id=game, start_time=start, end_time=start + length,
            duration_seconds=int(length.total_seconds()), is_active=False,
        ))
        self.db.commit()

    def awarded(self):
        rows = (
            self.db.query(models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id)
            .join(models.UserAchievement, models.UserAchievement.achievement_id == models.Achievement.id)
            .all()
        )
        return {key: (date, game_id) for key, date, game_id in rows}

    def settings(self, **values):
        self.db.add(models.UserSettings(user_id=1, **values))
        self.db.commit()

    async def test_star_wars_day_needs_a_star_wars_game_and_names_it(self):
        self.play(datetime.datetime(2027, 5, 4, 20), game="g1")  # the day, but not the game
        await self.view.external_days(self.db, USER)
        self.assertNotIn("STAR_WARS_DAY_LIFETIME", self.awarded())
        self.play(datetime.datetime(2027, 5, 5, 20), game="sw")  # the game, but not the day
        await self.view.external_days(self.db, USER)
        self.assertNotIn("STAR_WARS_DAY_LIFETIME", self.awarded())
        self.play(datetime.datetime(2028, 5, 4, 20), game="sw")
        await self.view.external_days(self.db, USER)
        await self.view.external_days(self.db, USER)  # and it is earned once
        self.assertEqual(self.awarded()["STAR_WARS_DAY_LIFETIME"], (datetime.date(2028, 5, 4), "sw"))
        self.assertIn("STAR WARS Jedi", self.message(0))

    def message(self, index):
        return self.sent.await_args_list[index].args[0]

    async def test_mario_day_is_the_10th_of_march_with_a_mario_game(self):
        self.play(datetime.datetime(2027, 3, 10, 18), game="mario")
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded()["MARIO_DAY_LIFETIME"], (datetime.date(2027, 3, 10), "mario"))

    async def test_a_session_of_any_length_counts(self):
        self.play(datetime.datetime(2027, 3, 10, 18), game="mario", minutes=1)
        await self.view.external_days(self.db, USER)
        self.assertIn("MARIO_DAY_LIFETIME", self.awarded())

    async def test_the_leap_day_is_the_day_a_session_started_not_the_one_it_reached(self):
        self.play(datetime.datetime(2028, 2, 28, 23, 30), hours=2)  # it ends on the 29th, but it started on the 28th
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.play(datetime.datetime(2028, 2, 29, 0, 10), hours=1)
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded()["LEAP_DAY_LIFETIME"], (datetime.date(2028, 2, 29), None))

    async def test_a_timer_that_starts_earns_it_before_any_session_is_finished(self):
        started = [ach_module.Played("sw", datetime.datetime(2027, 5, 4, 20, 5))]  # running: not in the database yet
        await self.view.external_days(self.db, USER, played=started)
        await self.view.archaeologist(self.db, USER, played=started)
        self.assertEqual(self.awarded(), {"STAR_WARS_DAY_LIFETIME": (datetime.date(2027, 5, 4), "sw")})  # 2019: not 25 years old
        started = [ach_module.Played("sh", datetime.datetime(2027, 5, 5, 20, 5))]
        await self.view.archaeologist(self.db, USER, played=started)
        self.assertEqual(self.awarded()["ARCHAEOLOGIST_LIFETIME"], (datetime.date(2027, 5, 5), "sh"))

    async def test_a_timer_that_starts_before_the_season_it_counts_from_does_not_count(self):
        view = Achievements(season=seasons.ALL, since=2028)
        await view.external_days(self.db, USER, played=[ach_module.Played("sw", datetime.datetime(2027, 5, 4, 20))])
        self.assertEqual(self.awarded(), {})

    async def test_the_start_of_a_timer_is_wired_to_the_orchestration(self):
        started = [ach_module.Played("sw", datetime.datetime(2027, 5, 4, 20))]
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        with mock.patch.object(weather, "codes_for_days", return_value={datetime.date(2027, 5, 4): [95] * 24}):
            for view in Achievements().lifetime_views(self.db):
                await view.external_days(self.db, USER, played=started)
                await view.weather(self.db, USER, played=started)
        self.assertEqual(set(self.awarded()), {"STAR_WARS_DAY_LIFETIME", "STORM_LIFETIME"})

    async def test_a_birthday_needs_a_birth_date(self):
        self.play(datetime.datetime(2027, 6, 15, 12))
        await self.view.external_days(self.db, USER)
        self.assertNotIn("BIRTHDAY_LIFETIME", self.awarded())
        self.settings(birth_date=datetime.date(1990, 6, 15))
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded()["BIRTHDAY_LIFETIME"], (datetime.date(2027, 6, 15), None))

    async def test_the_sky_full_moon_eclipses_and_solstices(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.7026)
        self.play(datetime.datetime(2027, 1, 22, 20))  # full moon at 12:17 UTC
        self.play(datetime.datetime(2027, 8, 2, 20))  # total solar eclipse, seen from Madrid at 0.88
        self.play(datetime.datetime(2029, 6, 25, 22))  # total lunar eclipse in the night of the 25th, after the sunset in Madrid
        self.play(datetime.datetime(2027, 6, 21, 20))  # summer solstice
        self.play(datetime.datetime(2027, 12, 22, 20))  # winter solstice
        self.play(datetime.datetime(2027, 3, 20, 20))  # spring equinox
        self.play(datetime.datetime(2027, 9, 23, 20))  # autumn equinox
        await self.view.external_days(self.db, USER)
        got = {key: date for key, (date, _) in self.awarded().items()}
        self.assertEqual(got, {
            "FULL_MOON_LIFETIME": datetime.date(2027, 1, 22),
            "SOLAR_ECLIPSE_LIFETIME": datetime.date(2027, 8, 2),
            "LUNAR_ECLIPSE_LIFETIME": datetime.date(2029, 6, 25),
            "SUMMER_SOLSTICE_LIFETIME": datetime.date(2027, 6, 21),
            "WINTER_SOLSTICE_LIFETIME": datetime.date(2027, 12, 22),
            "SPRING_EQUINOX_LIFETIME": datetime.date(2027, 3, 20),
            "AUTUMN_EQUINOX_LIFETIME": datetime.date(2027, 9, 23),
        })

    async def test_the_eclipses_need_the_city_of_the_player_and_a_visible_eclipse(self):
        self.play(datetime.datetime(2027, 8, 2, 20))
        self.play(datetime.datetime(2029, 6, 25, 22))
        await self.view.external_days(self.db, USER)
        self.assertFalse({"SOLAR_ECLIPSE_LIFETIME", "LUNAR_ECLIPSE_LIFETIME"} & set(self.awarded()))  # no city, no eclipse
        self.settings(place_name="Buenos Aires", place_latitude=-34.6, place_longitude=-58.4)
        await self.view.external_days(self.db, USER)
        self.assertNotIn("SOLAR_ECLIPSE_LIFETIME", self.awarded())  # the eclipse of August 2027 is not seen from there

    async def test_a_lunar_eclipse_asks_for_a_timer_started_in_its_night_after_the_sunset(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.7026)
        self.play(datetime.datetime(2029, 6, 25, 12))  # the day of the eclipse's night, but before the sunset (19:49 UTC)
        self.play(datetime.datetime(2029, 6, 26, 12))  # the day it was over, after the sunrise (4:46 UTC)
        await self.view.external_days(self.db, USER)
        self.assertNotIn("LUNAR_ECLIPSE_LIFETIME", self.awarded())
        self.play(datetime.datetime(2029, 6, 26, 1, 30))  # past midnight, still in the night
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded()["LUNAR_ECLIPSE_LIFETIME"], (datetime.date(2029, 6, 26), None))

    async def test_an_ordinary_day_earns_nothing(self):
        self.play(datetime.datetime(2027, 2, 2, 20))
        await self.view.external_days(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_only_what_was_played_from_its_season_on_counts(self):
        self.db.query(models.Achievement).filter_by(key="LEAP_DAY_LIFETIME").update({"valid_from_season": 2029})
        self.db.commit()
        self.play(datetime.datetime(2028, 2, 29, 20))
        for view in Achievements().lifetime_views(self.db):
            await view.external_days(self.db, USER)
        self.assertNotIn("LEAP_DAY_LIFETIME", self.awarded())

    async def test_the_archaeologist_needs_a_game_of_25_years_on_the_day_it_was_played(self):
        self.play(datetime.datetime(2027, 3, 1, 20), game="new")
        await self.view.archaeologist(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.play(datetime.datetime(2027, 3, 2, 20), game="sh")  # 2001: 25 years in September 2026
        await self.view.archaeologist(self.db, USER)
        self.assertEqual(self.awarded()["ARCHAEOLOGIST_LIFETIME"], (datetime.date(2027, 3, 2), "sh"))

    async def test_a_game_without_release_date_is_never_archaeological(self):
        self.db.add(models.Game(id="x", name="Unknown", slug="x"))
        self.db.commit()
        self.play(datetime.datetime(2027, 3, 1, 20), game="x")
        await self.view.archaeologist(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_a_game_of_the_year_the_player_was_born_in(self):
        self.play(datetime.datetime(2027, 3, 1, 20), game="g1")  # 1993
        await self.view.birth_year_game(self.db, USER)
        self.assertEqual(self.awarded(), {})  # no birth date yet
        self.settings(birth_date=datetime.date(1993, 8, 30))
        await self.view.birth_year_game(self.db, USER)
        self.assertEqual(self.awarded()["BIRTH_YEAR_GAME_LIFETIME"], (datetime.date(2027, 3, 1), "g1"))

    async def test_a_game_of_another_year_or_without_date_is_not_of_their_year(self):
        self.db.add(models.Game(id="x", name="Unknown", slug="x"))
        self.db.commit()
        self.settings(birth_date=datetime.date(1994, 1, 1))
        self.play(datetime.datetime(2027, 3, 1, 20), game="g1")  # 1993: a year before
        self.play(datetime.datetime(2027, 3, 2, 20), game="x")
        await self.view.birth_year_game(self.db, USER)
        self.assertEqual(self.awarded(), {})
        await self.view.birth_year_game(self.db, USER, played=[ach_module.Played("g1", datetime.datetime(2027, 3, 3, 20))])
        self.assertEqual(self.awarded(), {})

    def stormy(self, day, hours):
        codes = [0] * 24
        for hour in hours:
            codes[hour] = 95
        return {day: codes}

    async def test_a_storm_while_playing_at_the_city_of_the_player(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        self.play(datetime.datetime(2027, 7, 1, 21, 30), hours=1)
        codes = self.stormy(datetime.date(2027, 7, 1), [21])  # the hour it started in
        with mock.patch.object(weather, "codes_for_days", return_value=codes) as asked:
            await self.view.weather(self.db, USER)
        self.assertEqual(self.awarded()["STORM_LIFETIME"], (datetime.date(2027, 7, 1), None))
        self.assertEqual(asked.call_args.args[:3], (self.db, 40.4165, -3.70256))
        self.assertEqual(set(asked.call_args.args[3]), {datetime.date(2027, 7, 1)})

    async def test_a_storm_in_another_hour_than_the_one_it_started_in_is_not_enough(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        self.play(datetime.datetime(2027, 7, 1, 21, 30), hours=1)
        with mock.patch.object(weather, "codes_for_days", return_value=self.stormy(datetime.date(2027, 7, 1), [22])):
            await self.view.weather(self.db, USER)
        self.assertEqual(self.awarded(), {})

    async def test_fog_counts_only_with_a_horror_game(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        foggy = {datetime.date(2027, 11, 3): [45] * 24}
        self.play(datetime.datetime(2027, 11, 3, 21), game="g1")
        with mock.patch.object(weather, "codes_for_days", return_value=foggy):
            await self.view.weather(self.db, USER)
        self.assertEqual(self.awarded(), {})
        self.play(datetime.datetime(2027, 11, 3, 23), game="sh")
        with mock.patch.object(weather, "codes_for_days", return_value=foggy):
            await self.view.weather(self.db, USER)
        self.assertEqual(self.awarded()["HORROR_FOG_LIFETIME"], (datetime.date(2027, 11, 3), "sh"))
        self.assertIn("Silent Hill 2", self.message(0))

    async def test_without_a_city_the_weather_is_not_even_asked(self):
        self.play(datetime.datetime(2027, 7, 1, 21, 30))
        with mock.patch.object(weather, "codes_for_days") as asked:
            await self.view.weather(self.db, USER)
        asked.assert_not_called()
        self.assertEqual(self.awarded(), {})

    async def test_when_open_meteo_is_down_nothing_is_decided_and_a_recalculation_is_told_so(self):
        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        self.play(datetime.datetime(2027, 7, 1, 21, 30))
        undecided = set()
        view = Achievements(season=seasons.ALL, since=2023, collected=[], undecided=undecided)
        with mock.patch.object(weather, "codes_for_days", side_effect=weather.WeatherUnavailable("down")):
            await view.weather(self.db, USER)
            await self.view.weather(self.db, USER)  # a live check just tries again next time
        self.assertEqual(undecided, {"STORM_LIFETIME", "HORROR_FOG_LIFETIME"})
        self.assertEqual(self.awarded(), {})

    async def test_the_orchestration_runs_them_and_a_recalculation_keeps_what_it_could_not_tell(self):
        from src.crud import achievements_recalc

        self.settings(place_name="Madrid", place_latitude=40.4165, place_longitude=-3.70256)
        self.play(datetime.datetime(2027, 5, 4, 20), game="sw")
        self.play(datetime.datetime(2027, 7, 1, 21, 30))
        stormy = self.stormy(datetime.date(2027, 7, 1), [21])
        user = self.db.merge(models.User(id=1, name="Ana", username="ana"))
        with mock.patch.object(weather, "codes_for_days", return_value=stormy):
            await actions.check_user_lifetime(self.db, user)
        self.assertEqual(set(self.awarded()), {"STAR_WARS_DAY_LIFETIME", "STORM_LIFETIME", "ARCHAEOLOGIST_LIFETIME"})  # Doom is from 1993
        with mock.patch.object(weather, "codes_for_days", side_effect=weather.WeatherUnavailable("down")):
            expected, undecided = await achievements_recalc._expected_lifetime(self.db, user)
        self.assertIn("STAR_WARS_DAY_LIFETIME", expected)  # what needs no weather is worked out as ever
        self.assertNotIn("STORM_LIFETIME", expected)
        self.assertIn("STORM_LIFETIME", undecided)  # so the recalculation leaves it alone instead of revoking it


LEGACY_2023 = {  # the achievements that existed before the rule 'every new one starts in 2027'
    "ALL_TOGETHER", "COMPLETED_1000_GAMES_LIFETIME", "COMPLETED_100_GAMES", "COMPLETED_100_GAMES_LIFETIME",
    "COMPLETED_10_GAMES", "COMPLETED_1_GAME", "COMPLETED_200_GAMES_LIFETIME", "COMPLETED_25_GAMES",
    "COMPLETED_42_GAMES", "COMPLETED_500_GAMES_LIFETIME", "COMPLETED_5_GAMES", "COMPLETED_IN_A_DAY", "EARLY_RISER",
    "HAPPY_NEW_YEAR", "JUST_IN_TIME", "NOCTURNAL", "PLAYED_10000_HOURS_LIFETIME", "PLAYED_1000_DAYS_LIFETIME",
    "PLAYED_1000_GAMES_LIFETIME", "PLAYED_1000_HOURS", "PLAYED_1000_HOURS_GAME", "PLAYED_1000_HOURS_GAME_LIFETIME",
    "PLAYED_1000_HOURS_LIFETIME", "PLAYED_100_DAYS", "PLAYED_100_DAYS_LIFETIME", "PLAYED_100_GAMES",
    "PLAYED_100_GAMES_LIFETIME", "PLAYED_100_HOURS", "PLAYED_100_HOURS_GAME", "PLAYED_10_GAMES",
    "PLAYED_10_GAMES_DAY", "PLAYED_12_HOURS_DAY", "PLAYED_15_DAYS", "PLAYED_16_HOURS_DAY",
    "PLAYED_2000_DAYS_LIFETIME", "PLAYED_2000_HOURS_LIFETIME", "PLAYED_200_DAYS", "PLAYED_200_DAYS_LIFETIME",
    "PLAYED_200_GAMES_LIFETIME", "PLAYED_200_HOURS", "PLAYED_300_DAYS", "PLAYED_30_DAYS", "PLAYED_365_DAYS",
    "PLAYED_42_GAMES", "PLAYED_4_HOURS_DAY", "PLAYED_4_HOURS_SESSION", "PLAYED_5000_DAYS_LIFETIME",
    "PLAYED_5000_HOURS_LIFETIME", "PLAYED_500_DAYS_LIFETIME", "PLAYED_500_GAMES_LIFETIME", "PLAYED_500_HOURS",
    "PLAYED_500_HOURS_GAME", "PLAYED_500_HOURS_LIFETIME", "PLAYED_50_GAMES", "PLAYED_5_GAMES_DAY", "PLAYED_60_DAYS",
    "PLAYED_7_DAYS", "PLAYED_8_HOURS_DAY", "PLAYED_8_HOURS_GAME_DAY", "PLAYED_8_HOURS_SESSION",
    "PLAYED_LESS_5_MIN_SESSION", "PRODIGAL_SON", "RELEASE_DAY", "SAVED_BY_THE_BELL", "STREAK_100_DAYS",
    "STREAK_15_DAYS", "STREAK_200_DAYS", "STREAK_300_DAYS", "STREAK_30_DAYS", "STREAK_365_DAYS", "STREAK_60_DAYS",
    "STREAK_7_DAYS", "TEAMWORK", "WORK_WEEK",
}


class CatalogueTests(unittest.TestCase):
    def test_every_achievement_says_the_season_it_starts_in(self):
        without = [ach.name for ach in ach_module.AchievementsElems if "since" not in ach.value]
        self.assertEqual(without, [])  # one added without it would not be created at all
        for ach in ach_module.AchievementsElems:
            # the first ones count the history since the first season; every one added since starts in 2027 (a new
            # achievement is not retroactive, and the day there is a reason for it to be, this list is where it is said)
            self.assertEqual(first_season(ach), 2023 if ach.name in LEGACY_2023 else 2027, ach.name)
        self.assertEqual(LEGACY_2023 - {ach.name for ach in ach_module.AchievementsElems}, set())

    def test_the_ones_about_the_world_outside_the_app_are_all_hidden_and_without_a_season_limit(self):
        for ach in ach_module.EXTERNAL_LIFETIME:
            self.assertTrue(is_lifetime(ach.name), ach.name)
            self.assertTrue(ach.value.get("secret"), ach.name)
            self.assertEqual(ach.value["message"].count("{}"), 2 if ach.name in WITH_A_GAME else 1, ach.name)


    def test_the_levels_and_secrets_the_definitions_give_are_valid(self):
        for ach in ach_module.AchievementsElems:
            self.assertIn(ach.value.get("special", 0), (0, 1, 2, 3), ach.name)
            self.assertIn(ach.value.get("secret", False), (True, False), ach.name)

    def test_a_new_row_is_created_as_special_or_secret_when_its_definition_says_so(self):
        db = make_session()
        Achievements().populate_achievements(db)
        rows = {row.key: row for row in db.query(models.Achievement)}
        self.assertEqual((rows["PLAYED_42_GAMES"].special, rows["PLAYED_42_GAMES"].secret), (1, False))
        self.assertEqual((rows["JUST_IN_TIME"].special, rows["JUST_IN_TIME"].secret), (1, True))
        self.assertEqual((rows["EARLY_RISER"].special, rows["EARLY_RISER"].secret), (0, True))
        self.assertEqual((rows["PLAYED_7_DAYS"].special, rows["PLAYED_7_DAYS"].secret), (0, False))
        for ach in ach_module.AchievementsElems:
            self.assertEqual(rows[ach.name].special, ach.value.get("special", 0), ach.name)

    def test_what_the_review_migration_sets_is_about_achievements_that_exist_and_says_what_the_code_says(self):
        from tests.test_migrations import load_script_directory

        migration = load_script_directory().get_revision("033_achievement_review").module
        by_name = {ach.name: ach for ach in ach_module.AchievementsElems}
        self.assertLessEqual({key for key, _, _ in migration.SPECIAL} | set(migration.SECRET), set(by_name))
        for key, _, level in migration.SPECIAL:
            self.assertEqual(by_name[key].value.get("special", 0), level, key)  # the snapshot is what the code says now
        for key in migration.SECRET:
            self.assertTrue(by_name[key].value.get("secret"), key)

    def test_what_the_migration_sets_is_about_achievements_that_exist(self):
        from tests.test_migrations import load_script_directory

        migration = load_script_directory().get_revision("029_achievement_levels").module
        names = {ach.name for ach in ach_module.AchievementsElems}
        self.assertLessEqual({key for key, _ in migration.SPECIAL} | set(migration.SECRET), names)  # a typo would silently do nothing
        self.assertTrue(all(level in (1, 2, 3) for _, level in migration.SPECIAL))


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
