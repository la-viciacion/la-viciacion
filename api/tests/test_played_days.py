import datetime
import unittest

from src.crud import time_entries
from src.database import models
from src.utils import seasons
from tests.sqlite_db import make_session

YEAR = 2026
D = datetime.date


def at(year, month, day, hour=10, minute=0):
    return datetime.datetime(year, month, day, hour, minute)


class PlayedDaysTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bea", username="bea", is_active=1),
            models.Game(id="g1", name="Doom"),
        ])
        self.db.commit()

    def play(self, start, end, user_id=1):
        self.db.add(models.GameTimer(
            user_id=user_id, game_id="g1", start_time=start, end_time=end,
            duration_seconds=int((end - start).total_seconds()), is_active=False,
        ))
        self.db.commit()

    def days(self, season=YEAR, user_id=1):
        return time_entries.get_played_days(self.db, user_id, season=season)

    def test_a_session_counts_for_its_day(self):
        self.play(at(YEAR, 3, 1), at(YEAR, 3, 1, 11))
        self.assertEqual(self.days(), [D(YEAR, 3, 1)])

    def test_a_session_across_midnight_counts_for_both_days(self):
        self.play(at(YEAR, 3, 1, 23, 30), at(YEAR, 3, 2, 0, 30))
        self.assertEqual(self.days(), [D(YEAR, 3, 1), D(YEAR, 3, 2)])

    def test_a_session_of_less_than_ten_minutes_gives_no_day(self):
        self.play(at(YEAR, 3, 1), at(YEAR, 3, 1, 10, 9, ) + datetime.timedelta(seconds=59))
        self.assertEqual(self.days(), [])

    def test_ten_minutes_is_enough(self):
        self.play(at(YEAR, 3, 1), at(YEAR, 3, 1, 10, 10))
        self.assertEqual(self.days(), [D(YEAR, 3, 1)])

    def test_the_new_year_session_gives_each_season_its_own_day(self):
        self.play(at(YEAR - 1, 12, 31, 23, 0), at(YEAR, 1, 1, 1, 0))
        self.assertEqual(self.days(YEAR - 1), [D(YEAR - 1, 12, 31)])
        self.assertEqual(self.days(YEAR), [D(YEAR, 1, 1)])
        self.assertEqual(self.days(seasons.ALL), [D(YEAR - 1, 12, 31), D(YEAR, 1, 1)])

    def test_a_streak_does_not_cross_into_the_next_season(self):
        for day in (30, 31):
            self.play(at(YEAR - 1, 12, day), at(YEAR - 1, 12, day, 11))
        for day in (1, 2):
            self.play(at(YEAR, 1, day), at(YEAR, 1, day, 11))
        self.assertEqual(self.days(), [D(YEAR, 1, 1), D(YEAR, 1, 2)])

    def test_a_day_with_several_sessions_is_one_day(self):
        self.play(at(YEAR, 3, 1, 9), at(YEAR, 3, 1, 10))
        self.play(at(YEAR, 3, 1, 12), at(YEAR, 3, 1, 13))
        self.assertEqual(self.days(), [D(YEAR, 3, 1)])

    def test_every_player_is_a_key_with_only_their_own_days(self):
        self.play(at(YEAR, 3, 1), at(YEAR, 3, 1, 11), user_id=2)
        got = time_entries.players_played_dates(self.db, season=YEAR)
        self.assertEqual(got, {1: [], 2: [D(YEAR, 3, 1)]})


if __name__ == "__main__":
    unittest.main()
