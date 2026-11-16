"""The hours in a game (utils/challenges.py, crud/challenges.py) against a real, in-memory database: what is counted, the
launch of both templates and what the history and the list of the admin say of a challenge that has nothing to meet."""
import datetime
import unittest

from src.crud import challenges as crud
from src.database import models
from src.utils import challenges
from src.utils.challenges import ChallengeError
from tests.sqlite_db import make_session

TODAY = datetime.date(2026, 10, 15)
HOUR = 3600


class GameHoursDbTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.ana = models.User(id=1, name="Ana", username="ana", is_active=1, is_admin=1)
        self.bea = models.User(id=2, name="Bea", username="bea", is_active=1, is_admin=0)
        self.db.add_all([self.ana, self.bea, models.Game(id="hades", name="Hades"), models.Game(id="doom", name="Doom")])
        self.db.commit()

    def play(self, user_id, game_id, day, hours, hour=10, finished=True):
        start = datetime.datetime.combine(day, datetime.time(hour))
        self.db.add(models.GameTimer(
            user_id=user_id, game_id=game_id, platform="pc", start_time=start, end_time=start + datetime.timedelta(hours=hours),
            duration_seconds=round(hours * HOUR), is_active=not finished,
        ))
        self.db.commit()

    def weekend(self, **options):
        return crud.create(self.db, self.ana, "game_hours", {"game_id": "hades", "period": "range", "starts_on": "2026-10-17", "ends_on": "2026-10-18", **options}, TODAY)

    def test_only_the_finished_sessions_of_that_game_within_the_period_are_summed(self):
        challenge = self.weekend()
        saturday, sunday = datetime.date(2026, 10, 17), datetime.date(2026, 10, 18)
        self.play(1, "hades", saturday, 2)
        self.play(1, "hades", sunday, 1.5)
        self.play(2, "hades", saturday, 4)
        self.play(2, "hades", datetime.date(2026, 10, 19), 3)  # after the period
        self.play(2, "doom", saturday, 5)  # another game
        self.play(1, "hades", sunday, 1, hour=18, finished=False)  # still running
        progress = crud.progress_of(self.db, challenge)
        self.assertEqual([(p["name"], p["seconds"]) for p in progress["players"]], [("Bea", 4 * HOUR), ("Ana", round(3.5 * HOUR))])
        self.assertEqual(progress["total_seconds"], round(7.5 * HOUR))
        self.assertTrue(all(p["accumulate"] and "done" not in p for p in progress["players"]))

    def test_the_personal_one_counts_only_its_owner_from_the_moment_it_was_launched(self):
        challenge = crud.create(self.db, self.bea, "own_game_hours", {"game_id": "hades", "duration": "week"}, TODAY)
        self.assertEqual((challenge.scope, challenge.owner_user_id, challenge.title), ("user", 2, "Horas en Hades"))
        challenge.created_at = datetime.datetime.combine(TODAY, datetime.time(9))  # the test's clock is not the database's
        self.db.commit()
        self.play(2, "hades", TODAY, 3, hour=7)  # earlier that day: before it was launched
        self.play(2, "hades", TODAY + datetime.timedelta(days=1), 2)
        self.play(1, "hades", TODAY + datetime.timedelta(days=1), 6)  # somebody else's hours are not theirs
        progress = crud.progress_of(self.db, challenge)
        self.assertEqual([(p["user_id"], p["seconds"]) for p in progress["players"]], [(2, 2 * HOUR)])

    def test_two_equal_ones_are_one_challenge_and_a_missing_game_is_refused(self):
        self.weekend()
        with self.assertRaises(challenges.ChallengeConflict):
            self.weekend()
        with self.assertRaises(ChallengeError):
            self.weekend(game_id="nope")

    def test_the_history_and_the_list_say_the_hours_and_not_a_result(self):
        challenge = self.weekend(versus=True)
        self.play(1, "hades", datetime.date(2026, 10, 17), 3)
        self.play(2, "hades", datetime.date(2026, 10, 18), 1)
        after = datetime.date(2026, 10, 20)
        entry = crud.history(self.db, 1, after)[0]
        self.assertEqual((entry["kind"], entry["done"], entry["seconds"], entry["group_done"]), ("game_hours", False, 3 * HOUR, None))
        self.assertEqual(crud.history(self.db, 2, after)[0]["seconds"], HOUR)
        shown = crud.view(self.db, challenge, 1, after)
        self.assertEqual([(p["name"], p["position"], p["winner"]) for p in shown["progress"]["players"]], [("Ana", 1, True), ("Bea", 2, False)])


if __name__ == "__main__":
    unittest.main()
