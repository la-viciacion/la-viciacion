"""The game page through real requests: who of the group has a game, their hours, completions and ratings
(MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta

from src.database import models
from src.utils import seasons
from tests.api_support import ApiTestCase
from tests import clock
from tests.clock import ago

TODAY = clock.today


class GameOverviewTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.cai = self.user("cai")
        self.gone = self.user("gone", active=False)
        self.game("celeste", "Celeste", genres="Platformer, Indie", dev="Maddy", avg_time=30000)
        self.game("hades", "Hades")

    def overview(self, game="celeste", as_user="ana"):
        return self.api("GET", f"/games/{game}/overview", as_user=as_user)

    def rate(self, user_id, game_id, score):
        from src.database import database

        with database.SessionLocal() as db:
            db.add(models.GameScore(user_id=user_id, game_id=game_id, score=score))
            db.commit()

    def test_it_describes_the_game(self):
        body = self.overview().json()
        self.assertEqual(
            (body["game"]["id"], body["game"]["name"], body["game"]["genres"], body["game"]["dev"], body["game"]["avg_time"]),
            ("celeste", "Celeste", ["Platformer", "Indie"], "Maddy", 30000),
        )
        self.assertEqual(body["players"], [])
        self.assertEqual(body["summary"], {"players": 0, "played_seconds": 0, "completed_by": 0, "score_count": 0, "score_mean": None})

    def test_an_unknown_game_is_a_404_and_a_login_is_needed(self):
        self.assertEqual(self.overview(game="nope").status_code, 404)
        self.assertEqual(self.api("GET", "/games/celeste/overview").status_code, 401)

    def test_it_lists_the_players_with_their_hours_the_most_played_first(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "switch")
        self.session(self.ana, "celeste", ago(hours=5), 60)
        self.session(self.bea, "celeste", ago(hours=3), 90)
        self.session(self.bea, "celeste", ago(hours=1), 30)
        body = self.overview().json()
        self.assertEqual([(p["name"], p["played_seconds"], p["sessions"]) for p in body["players"]], [("Bea", 7200, 2), ("Ana", 3600, 1)])
        self.assertEqual([p["is_me"] for p in body["players"]], [False, True])
        self.assertEqual([p["is_active"] for p in body["players"]], [True, True])
        self.assertEqual((body["summary"]["players"], body["summary"]["played_seconds"]), (2, 10800))

    def test_seasons_completions_and_ratings(self):
        last = seasons.current() - 1
        self.library_entry(self.ana, "celeste", datetime.date(last, 3, 1), "pc", completed=1, completed_date=datetime.date(last, 4, 1))
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "pc")
        self.rate(self.ana, "celeste", 90)
        self.rate(self.bea, "celeste", 70)
        body = self.overview().json()
        by_name = {p["name"]: p for p in body["players"]}
        self.assertEqual((by_name["Ana"]["seasons"], by_name["Ana"]["completed"], by_name["Ana"]["completions"], by_name["Ana"]["score"]),
                         ([seasons.current(), last], True, 1, 90))
        self.assertEqual((by_name["Bea"]["completed"], by_name["Bea"]["score"]), (False, 70))
        self.assertEqual((body["summary"]["completed_by"], body["summary"]["score_count"], body["summary"]["score_mean"]), (1, 2, 80.0))

    def test_inactive_players_are_listed_and_other_games_are_left_out(self):
        self.library_entry(self.gone, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.rate(self.gone, "celeste", 5)
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        players = self.overview().json()["players"]
        self.assertEqual([(p["name"], p["completed"], p["score"]) for p in players], [("Gone", True, 5)])
        self.assertFalse(players[0]["is_active"])

    def test_who_is_playing_it_right_now_is_marked_unless_stale_or_hidden(self):
        for user in (self.ana, self.bea, self.cai):
            self.library_entry(user, "celeste", TODAY(), "pc")
        for user in ("ana", "bea", "cai"):
            self.api("POST", "/timers/start", as_user=user, json={"user_id": {"ana": self.ana, "bea": self.bea, "cai": self.cai}[user],
                                                                    "game_id": "celeste", "platform": "pc"})
        from sqlalchemy import text

        with self.engine.begin() as conn:  # Cai forgot theirs
            conn.execute(text("UPDATE game_timers SET start_time = start_time - INTERVAL 8 HOUR WHERE user_id = :u"), {"u": self.cai})
        self.api("PATCH", "/users/bea/settings", as_user="bea", json={"show_playing": False})
        playing = {p["name"]: p["playing"] for p in self.overview(as_user="ana").json()["players"]}
        self.assertEqual(playing, {"Ana": True, "Bea": False, "Cai": False})
