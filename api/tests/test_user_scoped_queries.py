import datetime
import unittest

from sqlalchemy import event

from src.crud import time_entries, users
from src.database import models
from tests.sqlite_db import make_session

YEAR = datetime.date.today().year


def session(db, user, game, day, hours):
    start = datetime.datetime(YEAR, 3, day, 10)
    db.add(models.GameTimer(
        user_id=user, game_id=game, start_time=start, end_time=start + datetime.timedelta(hours=hours),
        duration_seconds=hours * 3600, is_active=False,
    ))


class UserScopedTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.User(id=1, name="Ana", username="ana", is_active=1), models.User(id=2, name="Bob", username="bob", is_active=1),
                         models.Game(id="g1", name="Doom"), models.Game(id="g2", name="Quake")])
        for user, game, day, hours in ((1, "g1", 1, 2), (1, "g1", 2, 1), (2, "g1", 3, 5), (2, "g2", 4, 1)):
            session(self.db, user, game, day, hours)
        self.db.commit()

    def rows(self, subquery):
        return {(r.user_id, r.game_id): r.played_time for r in self.db.execute(subquery.select()).all()}

    def test_entry_time_of_everybody_by_default(self):
        self.assertEqual(self.rows(time_entries.entry_played_time()),
                         {(1, "g1"): 3 * 3600, (2, "g1"): 5 * 3600, (2, "g2"): 3600})

    def test_entry_time_can_be_limited_to_one_user_inside_the_subquery(self):
        subquery = time_entries.entry_played_time(1)
        self.assertEqual(self.rows(subquery), {(1, "g1"): 3 * 3600})
        self.assertIn("user_id = ", str(subquery.element.compile()).split("GROUP BY")[0].split("WHERE")[-1])

    def test_last_played_can_be_limited_too(self):
        got = {(r.user_id, r.game_id) for r in self.db.execute(users._last_played_by_year(2).select()).all()}
        self.assertEqual(got, {(2, "g1"), (2, "g2")})


class AchievementsOrderTests(unittest.TestCase):
    def test_achievements_of_the_same_day_keep_a_stable_order(self):
        db = make_session()
        db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        db.add_all([models.Achievement(id=i, key=f"K{i}", title=f"T{i}") for i in (1, 2, 3)])
        day = datetime.date(YEAR, 4, 1)
        for achievement in (3, 1, 2):  # unlocked the same day, inserted out of id order
            db.add(models.UserAchievement(user_id=1, achievement_id=achievement, date=day))
        db.commit()
        got = users.get_achievements(db, "ana", YEAR)
        self.assertEqual([r.title for r in got], ["T3", "T1", "T2"])  # by unlock id, not by luck


if __name__ == "__main__":
    unittest.main()
