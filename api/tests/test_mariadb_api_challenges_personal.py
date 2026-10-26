"""The personal challenges made from the sessions and the lists (streak, long sessions, variety of genres, wishlist),
through real requests (MariaDB required, see api_support.py): their options and what counts for their progress."""
import asyncio
from datetime import datetime, timedelta

from src.database import database, models
from src.utils import actions
from tests import test_mariadb_api_challenges as base

TODAY = base.TODAY


class PersonalTestCase(base.ChallengesTestCase):
    def launch_personal(self, kind, as_user="ana", **options):
        return self.api("POST", "/challenges", as_user=as_user, json={"kind": kind, "options": options})

    def part(self, challenge_id, as_user="ana"):
        return self.api("GET", f"/challenges/{challenge_id}", as_user=as_user).json()["progress"]["players"][0]

    def backdate(self, challenge_id, days):
        """Move the start back, as if it had been launched `days` ago (a challenge always starts the day it is launched)."""
        with database.SessionLocal() as db:
            row = db.get(models.Challenge, challenge_id)
            row.starts_on = row.starts_on - timedelta(days=days)
            db.commit()

    def play(self, user, game, days_ago, minutes):
        """A session that began `days_ago` days back at noon, so it never crosses midnight."""
        start = datetime.combine(TODAY() - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=12)
        if not self.scalar("SELECT COUNT(*) FROM users_games WHERE user_id = :u AND game_id = :g", u=user, g=game):
            self.library_entry(user, game, start.date(), "pc")
        self.session(user, game, start, minutes)


class StreakTests(PersonalTestCase):
    def test_consecutive_days_inside_the_period_are_the_longest_run_and_short_sessions_do_not_count(self):
        challenge = self.launch_personal("streak", mode="consecutive", days=3, duration="week").json()
        self.assertEqual(challenge["title"], "Racha de 3 días")
        self.backdate(challenge["id"], 4)
        self.play(self.ana, "hades", 0, 30)
        self.play(self.ana, "hades", 1, 30)
        self.play(self.ana, "celeste", 2, 5)  # under 10 minutes: not a played day
        self.play(self.ana, "hades", 4, 30)
        part = self.part(challenge["id"])
        self.assertEqual((part["count"], part["unit"], part["done"]), (2, "days", False))  # today and yesterday; the 4th day back is apart
        self.play(self.ana, "hades", 2, 30)
        part = self.part(challenge["id"])
        self.assertEqual((part["count"], part["done"]), (3, True))  # the run of three; the day four back is not part of it

    def test_days_before_it_began_do_not_count_and_the_target_is_reached_exactly(self):
        challenge = self.launch_personal("streak", mode="days", days=2, duration="week").json()["id"]
        self.backdate(challenge, 3)
        self.play(self.ana, "hades", 5, 60)  # before the period
        self.play(self.bea, "hades", 0, 60)  # someone else
        self.assertEqual(self.part(challenge)["count"], 0)
        self.play(self.ana, "hades", 0, 60)
        self.assertEqual(self.part(challenge)["done"], False)  # one day of the two asked
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.session(self.ana, "celeste", datetime.combine(TODAY(), datetime.min.time()) + timedelta(hours=1), 20)  # same day
        self.assertEqual(self.part(challenge)["count"], 1)  # one day, however many sessions

    def test_the_options_are_checked(self):
        for options, fragment in (({"mode": "x", "days": 3}, "seguidos"), ({"mode": "days", "days": 1}, "entre 2 y 30"), ({"mode": "days", "days": 9, "duration": "week"}, "entre 2 y 7")):
            response = self.launch_personal("streak", **options)
            self.assertEqual(response.status_code, 400, options)
            self.assertIn(fragment, response.json()["detail"])


class LongSessionsTests(PersonalTestCase):
    def test_only_finished_sessions_of_that_length_from_the_start_count(self):
        challenge = self.launch_personal("long_sessions", sessions=2, minutes=60, duration="week").json()["id"]
        self.backdate(challenge, 5)
        self.play(self.ana, "hades", 0, 59)  # one minute short
        self.play(self.ana, "hades", 1, 60)
        self.play(self.ana, "celeste", 2, 180)
        self.play(self.ana, "celeste", 9, 300)  # before the period
        self.play(self.bea, "hades", 0, 300)
        part = self.part(challenge)
        self.assertEqual((part["count"], part["target_count"], part["unit"], part["done"]), (2, 2, "sessions", True))


class VarietyTests(PersonalTestCase):
    def setUp(self):
        super().setUp()
        self.game("dead-cells", "Dead Cells", genres="Action, Metroidvania")
        self.game("tetris", "Tetris", genres="Puzzle")
        self.game("hades-2", "Hades II", genres="Action,Roguelike")

    def test_a_genre_counts_once_it_reaches_the_hours_and_a_game_counts_in_each_of_its_genres(self):
        challenge = self.launch_personal("variety", genres=3, hours=1, duration="week").json()["id"]
        self.backdate(challenge, 3)
        self.play(self.ana, "dead-cells", 0, 90)  # Action and Metroidvania
        self.play(self.ana, "tetris", 0, 30)  # Puzzle: half an hour is not enough
        part = self.part(challenge)
        self.assertEqual((part["count"], part["unit"], part["done"]), (2, "genres", False))
        self.play(self.ana, "tetris", 1, 30)
        self.assertEqual(self.part(challenge)["count"], 3)
        self.assertTrue(self.part(challenge)["done"])

    def test_it_cannot_ask_for_more_genres_than_there_are(self):
        response = self.launch_personal("variety", genres=6)
        self.assertEqual(response.status_code, 400)
        self.assertIn("entre 2 y 4", response.json()["detail"])  # Action, Metroidvania, Puzzle and Roguelike


class WishlistTests(PersonalTestCase):
    def wish(self, user, game, days_ago=10):
        with database.SessionLocal() as db:
            db.add(models.UserWishlist(user_id=user, game_id=game, added_at=datetime.combine(TODAY() - timedelta(days=days_ago), datetime.min.time())))
            db.commit()

    def test_it_needs_pending_wishes_and_no_more_games_than_there_are(self):
        self.assertEqual(self.launch_personal("wishlist", mode="start", games=1).status_code, 400)
        self.wish(self.ana, "hades")
        self.library_entry(self.ana, "celeste", TODAY() - timedelta(days=30), "pc")
        self.wish(self.ana, "celeste")  # already in the library: not pending
        response = self.launch_personal("wishlist", mode="start", games=2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("entre 1 y 1", response.json()["detail"])
        self.assertEqual(self.launch_personal("wishlist", mode="start", games=1).json()["title"], "Empezar 1 deseado")

    def test_starting_a_wish_in_the_period_counts_and_a_wish_added_later_does_not(self):
        self.wish(self.ana, "hades")
        challenge = self.launch_personal("wishlist", mode="start", games=1, duration="week").json()["id"]
        self.assertEqual(self.part(challenge)["count"], 0)
        self.game("tetris", "Tetris")
        self.wish(self.ana, "tetris", days_ago=-1)  # wished after it began
        self.library_entry(self.ana, "tetris", TODAY(), "pc")
        self.assertEqual(self.part(challenge)["count"], 0)
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        part = self.part(challenge)
        self.assertEqual((part["count"], part["unit"], part["done"]), (1, "games", True))

    def test_completing_asks_for_the_completion_to_be_in_the_period(self):
        self.wish(self.ana, "hades")
        challenge = self.launch_personal("wishlist", mode="complete", games=1, duration="week").json()
        self.assertEqual(challenge["title"], "Completar 1 deseado")
        entry = self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.assertEqual(self.part(challenge["id"])["count"], 0)  # started, not completed
        with database.SessionLocal() as db:
            row = db.get(models.UserGame, entry)
            row.completed, row.completed_date = 1, TODAY()
            db.commit()
        self.assertTrue(self.part(challenge["id"])["done"])


class AchievementTests(PersonalTestCase):
    def earned(self):
        """Run the lifetime checks of Ana, as the check after a stopped timer does, and say what she has."""
        async def run():
            with database.SessionLocal() as db:
                await actions.check_user_lifetime(db, db.get(models.User, self.ana), silent=True)

        asyncio.run(run())
        return {key for (key,) in self.rows("SELECT a.`key` FROM users_achievements ua JOIN achievements a ON a.id = ua.achievement_id WHERE ua.user_id = :u", u=self.ana)}

    def test_a_met_challenge_earns_its_achievement_once_it_is_over_and_not_before(self):
        with database.SessionLocal() as db:  # new achievements count from 2027: this one is switched to the season under test
            db.query(models.Achievement).filter_by(key="CHALLENGES_1_LIFETIME").update({"valid_from_season": TODAY().year})
            db.commit()
        personal = self.launch_personal("long_sessions", sessions=1, minutes=30, duration="week").json()["id"]
        challenge = self.launch(min_hours_each=0.5, min_hours_total=0.5).json()["id"]  # a group one: the tiers count those
        self.play(self.ana, "hades", 0, 45)
        self.assertTrue(self.part(challenge)["done"] and self.part(personal)["done"])
        self.assertEqual(self.earned(), set())  # met, but still running
        with database.SessionLocal() as db:
            for challenge_id in (challenge, personal):
                row = db.get(models.Challenge, challenge_id)
                row.starts_on, row.ends_on = TODAY() - timedelta(days=10), TODAY() - timedelta(days=3)
            db.commit()
        self.play(self.ana, "hades", 5, 45)  # inside the period it has now
        self.assertEqual(self.earned(), {"CHALLENGES_1_LIFETIME"})
        self.assertEqual(self.scalar("SELECT DATE(ua.date) FROM users_achievements ua"), TODAY() - timedelta(days=3))  # dated the day it ended
        self.assertEqual(self.earned(), {"CHALLENGES_1_LIFETIME"})  # earned once
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM users_achievements"), 1)
