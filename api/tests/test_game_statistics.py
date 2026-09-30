import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.crud import games
from src.database import models


class UpdateTotalPlayedTimeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://")
        models.GameStatistics.__table__.create(engine)
        self.db = sessionmaker(bind=engine)()

    def rows(self):
        return {r.game_id: r.played_time for r in self.db.query(models.GameStatistics).all()}

    def test_creates_the_row_when_the_game_has_none(self):
        games.update_total_played_time(self.db, "g1", 3600)
        self.assertEqual(self.rows(), {"g1": 3600})

    def test_updates_the_existing_row_without_duplicating_it(self):
        games.update_total_played_time(self.db, "g1", 3600)
        games.update_total_played_time(self.db, "g1", 7200)
        self.assertEqual(self.rows(), {"g1": 7200})


if __name__ == "__main__":
    unittest.main()
