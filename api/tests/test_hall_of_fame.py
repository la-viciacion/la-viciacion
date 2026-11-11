import datetime
import unittest

from src.crud import hall_of_fame
from src.database import models
from src.routers import statistics
from tests import clock
from tests.sqlite_db import make_session

YEAR = clock.YEAR


class ChampionsTests(unittest.TestCase):
    ROWS = [
        {"user_id": 1, "name": "Ana", "played_time": 7200},
        {"user_id": 2, "name": "Bea", "played_time": 7200},
        {"user_id": 3, "name": "Cai", "played_time": 60},
    ]

    def test_the_highest_figure_wins_and_a_tie_gives_a_title_to_each(self):
        got = hall_of_fame.champions(self.ROWS, "played_time")
        self.assertEqual([(c["user_id"], c["value"]) for c in got], [(1, 7200), (2, 7200)])

    def test_nobody_wins_a_category_nobody_has_anything_in(self):
        rows = [{"user_id": 1, "name": "Ana", "played_time": 0}]
        self.assertEqual(hall_of_fame.champions(rows, "played_time"), [])
        self.assertEqual(hall_of_fame.champions([], "played_time"), [])


class HallOfFameTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bob", username="bob", is_active=0),  # left the group: still a champion of the past
            models.User(id=3, name="Dios", username="admin", is_active=1, is_admin=1),
            models.Game(id="g1", name="Doom"), models.Game(id="g2", name="Quake"),
        ])
        # last season: Bob 3 h in 2 days, Ana 1 h in 1 day, the emergency account 9 h; this season: Ana 1 h
        sessions = (
            (2, "g1", datetime.datetime(YEAR - 1, 3, 1, 10), 2), (2, "g1", datetime.datetime(YEAR - 1, 3, 2, 10), 1),
            (1, "g2", datetime.datetime(YEAR - 1, 4, 1, 10), 1), (3, "g1", datetime.datetime(YEAR - 1, 5, 1, 10), 9),
            (1, "g2", datetime.datetime(YEAR, 1, 10, 10), 1),
        )
        entries = set()
        for user_id, game_id, start, hours in sessions:
            if (user_id, game_id, start.year) not in entries:
                entries.add((user_id, game_id, start.year))
                self.db.add(models.UserGame(user_id=user_id, game_id=game_id, completed=1 if user_id == 1 else 0, started_date=start.date(), platform="pc"))
            self.db.add(models.GameTimer(
                user_id=user_id, game_id=game_id, start_time=start, end_time=start + datetime.timedelta(hours=hours),
                duration_seconds=hours * 3600, is_active=False,
            ))
        self.db.commit()

    def test_only_the_seasons_that_are_over_are_listed_newest_first(self):
        self.db.add(models.UserGame(user_id=1, game_id="g1", started_date=datetime.date(YEAR - 3, 2, 1), platform="pc"))
        self.db.commit()
        self.assertEqual(hall_of_fame.closed_seasons(self.db), [YEAR - 1, YEAR - 3])

    def test_each_category_has_its_champion_whether_active_or_not_and_never_the_emergency_account(self):
        champions = hall_of_fame.season_champions(self.db, YEAR - 1)
        self.assertEqual([(c["name"], c["value"]) for c in champions["hours"]], [("Bob", 10800)])
        self.assertEqual([(c["name"], c["value"]) for c in champions["days"]], [("Bob", 2)])
        self.assertEqual([(c["name"], c["value"]) for c in champions["streak"]], [("Bob", 2)])
        self.assertEqual([(c["name"], c["value"]) for c in champions["completed"]], [("Ana", 1)])
        self.assertEqual(champions["achievements"], [])  # nobody earned any

    def test_titles_add_up_over_the_seasons(self):
        got = hall_of_fame.hall_of_fame(self.db)
        self.assertEqual([s["season"] for s in got["seasons"]], [YEAR - 1])
        self.assertEqual([(t["name"], t["titles"]) for t in got["titles"]], [("Bob", 4), ("Ana", 2)])  # Ana: games played and completed on a tie or alone

    def test_the_endpoint_answers_the_same(self):
        self.assertEqual(statistics.get_hall_of_fame(db=self.db), hall_of_fame.hall_of_fame(self.db))
