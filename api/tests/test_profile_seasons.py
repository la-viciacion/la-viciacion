import datetime
import unittest
from unittest import mock

from src.crud import time_entries, users
from src.database import models
from src.utils import seasons
from tests.sqlite_db import make_session

YEAR = seasons.current()


def session(db, game, year, month, day, hours=1):
    start = datetime.datetime(year, month, day, 10)
    db.add(models.GameTimer(
        user_id=1, game_id=game, platform="pc", start_time=start,
        end_time=start + datetime.timedelta(hours=hours), duration_seconds=hours * 3600, is_active=False,
    ))


def with_dates(real):
    """SQLite's DATE() gives text where MariaDB gives dates."""
    def wrapper(*args, **kwargs):
        return tuple([datetime.date.fromisoformat(d) for d in days] for days in real(*args, **kwargs))
    return wrapper


class ProfileSeasonsTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(time_entries, "get_played_days", with_dates(time_entries.get_played_days))
        patch.start()
        self.addCleanup(patch.stop)
        self.db = make_session()
        self.user = models.User(id=1, name="Ana", username="ana", is_active=1)
        self.db.add_all([self.user, models.Game(id="doom", name="Doom"), models.Game(id="hades", name="Hades")])
        # last season: Doom (completed) 2 h; this one: Doom 1 h and Hades 3 h
        self.db.add_all([
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(YEAR - 1, 3, 1), completed=1, completed_date=datetime.date(YEAR - 1, 4, 1)),
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(YEAR, 3, 1), completed=0),
            models.UserGame(user_id=1, game_id="hades", platform="pc", started_date=datetime.date(YEAR, 3, 1), completed=0),
        ])
        session(self.db, "doom", YEAR - 1, 3, 1, hours=2)
        session(self.db, "doom", YEAR, 3, 1, hours=1)
        session(self.db, "hades", YEAR, 3, 2, hours=3)
        self.db.commit()

    def profile(self, season=None):
        return users.get_profile(self.db, self.user, season)

    def test_the_running_season_is_the_default(self):
        got = self.profile()
        self.assertEqual((got["season"], got["stats"]["played_time"], got["stats"]["played_games"]), (YEAR, 4 * 3600, 2))

    def test_a_past_season_has_its_own_figures(self):
        got = self.profile(YEAR - 1)
        self.assertEqual(got["stats"]["played_time"], 2 * 3600)
        self.assertEqual((got["stats"]["played_days"], got["stats"]["played_games"], got["stats"]["completed_games"]), (1, 1, 1))
        self.assertEqual([g["game_id"] for g in got["top_games"]], ["doom"])

    def test_the_total_adds_every_season_counting_a_game_once(self):
        got = self.profile(seasons.ALL)
        self.assertEqual(got["season"], "all")
        self.assertEqual(got["stats"]["played_time"], 6 * 3600)
        self.assertEqual((got["stats"]["played_days"], got["stats"]["played_games"], got["stats"]["completed_games"]), (3, 2, 1))
        # a game is one row, with its time of every season
        self.assertEqual({g["game_id"]: g["played_time"] for g in got["top_games"]}, {"doom": 3 * 3600, "hades": 3 * 3600})

    def test_the_seasons_of_the_user_come_newest_first_with_the_running_one(self):
        self.assertEqual(self.profile()["seasons"], [YEAR, YEAR - 1])
        other = models.User(id=2, name="Beto", username="beto", is_active=1)
        self.db.add(other)
        self.db.commit()
        self.assertEqual(users.get_profile(self.db, other)["seasons"], [YEAR])
