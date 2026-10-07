"""The activity of the group through real requests (MariaDB required, see api_support.py)."""
import datetime
from datetime import timedelta

from sqlalchemy import text

from src.database import database, models
from tests.api_support import ApiTestCase

TODAY = datetime.date.today


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


class ActivityTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.gone = self.user("gone", active=False)
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")

    def feed(self, as_user="ana", **params):
        return self.api("GET", "/activity", as_user=as_user, params=params).json()

    def rate(self, user_id, game_id, score):
        with database.SessionLocal() as db:
            db.add(models.GameScore(user_id=user_id, game_id=game_id, score=score))
            db.commit()

    def award(self, user_id, day, game_id=None):
        achievement = self.scalar("SELECT id FROM achievements ORDER BY id LIMIT 1")
        with database.SessionLocal() as db:
            db.add(models.UserAchievement(user_id=user_id, achievement_id=achievement, date=day, game_id=game_id))
            db.commit()
        return self.scalar("SELECT title FROM achievements WHERE id = :i", i=achievement)

    def test_it_needs_a_login_and_starts_empty(self):
        self.assertEqual(self.api("GET", "/activity").status_code, 401)
        self.assertEqual(self.feed(), {"items": [], "has_more": False})

    def test_it_tells_what_each_player_did_with_the_most_notable_first_within_a_day(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.session(self.ana, "celeste", datetime.datetime.combine(TODAY(), datetime.time(0, 10)), 60)  # early: always today
        self.session(self.ana, "celeste", datetime.datetime.combine(TODAY(), datetime.time(2, 0)), 30)
        self.rate(self.ana, "celeste", 88)
        title = self.award(self.ana, TODAY(), "celeste")
        items = self.feed()["items"]
        self.assertEqual([i["type"] for i in items], ["completed", "achievement", "rated", "started", "played"])
        by_type = {i["type"]: i for i in items}
        self.assertEqual((by_type["completed"]["score"], by_type["completed"]["game_name"], by_type["completed"]["name"]), (88, "Celeste", "Ana"))
        self.assertEqual(by_type["played"]["seconds"], 5400)  # the two sessions of the day, added up
        self.assertEqual(by_type["rated"]["score"], 88)
        self.assertEqual((by_type["achievement"]["title"], by_type["achievement"]["game_id"]), (title, "celeste"))
        self.assertTrue(all(i["day"] == TODAY().isoformat() for i in items))

    def test_a_secret_achievement_the_viewer_lacks_is_announced_without_saying_which(self):
        self.award(self.ana, TODAY(), "celeste")
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE achievements SET secret = 1"))
        item = self.feed(as_user="bea")["items"][0]
        self.assertEqual((item["type"], item["hidden"], item["title"], item["game_id"], item["name"]), ("achievement", True, None, None, "Ana"))

    def test_one_that_is_not_secret_is_told_in_full_to_everybody(self):
        title = self.award(self.ana, TODAY(), "celeste")
        item = self.feed(as_user="bea")["items"][0]
        self.assertEqual((item["hidden"], item["title"], item["game_id"]), (False, title, "celeste"))

    def test_newest_days_first_and_a_game_started_once_per_player(self):
        old = TODAY() - timedelta(days=10)
        self.library_entry(self.bea, "hades", old, "pc")
        self.library_entry(self.bea, "hades", old - timedelta(days=400), "switch")  # an earlier season: the first time is that one
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        items = self.feed()["items"]
        self.assertEqual([(i["type"], i["name"], i["day"]) for i in items], [
            ("started", "Ana", TODAY().isoformat()),
            ("started", "Bea", (old - timedelta(days=400)).isoformat()),
        ])

    def test_inactive_players_count_but_running_timers_are_left_out(self):
        self.library_entry(self.gone, "celeste", TODAY() - timedelta(days=2), "pc")
        self.api("POST", "/timers/start", as_user="ana", json={"user_id": self.ana, "game_id": "hades", "platform": "pc"})
        items = self.feed()["items"]
        self.assertEqual([(i["type"], i["name"]) for i in items], [("started", "Ana"), ("started", "Gone")])  # the entry the timer opened, no "played"

    def test_paging(self):
        for n in range(5):
            self.game(f"g{n}", f"Game {n}")
            self.library_entry(self.ana, f"g{n}", TODAY() - timedelta(days=n), "pc")
        first = self.feed(limit=2)
        self.assertEqual((len(first["items"]), first["has_more"]), (2, True))
        second = self.feed(limit=2, offset=2)
        self.assertEqual((len(second["items"]), second["has_more"]), (2, True))
        last = self.feed(limit=2, offset=4)
        self.assertEqual((len(last["items"]), last["has_more"]), (1, False))
        names = [i["game_name"] for page in (first, second, last) for i in page["items"]]
        self.assertEqual(names, [f"Game {n}" for n in range(5)])  # newest first, no repeats, none missing

    def test_the_bounds(self):
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
            self.assertEqual(self.api("GET", "/activity", as_user="ana", params=params).status_code, 422, params)
