"""The group's library through real requests (MariaDB required, see api_support.py)."""
import datetime

from src.database import database, models
from tests import clock
from tests.api_support import ApiTestCase
from tests.clock import ago

TODAY = clock.today


class GroupLibraryTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.cai = self.user("cai", active=False)
        self.god = self.user("admin", admin=True)  # the emergency account (models.GOD_USERNAME)
        self.game("celeste", "Celeste", genres="Platformer, Indie")
        self.game("hades", "Hades", genres="Roguelike, Indie")
        self.game("doom", "Doom", genres="Shooter")
        self.game("limbo", "Limbo", genres="Platformer")
        self.game("tetris", "Tetris")

    def library(self, as_user="ana"):
        return self.api("GET", "/group/library", as_user=as_user)

    def rate(self, user, game, score):
        with database.SessionLocal() as db:
            db.add(models.GameScore(user_id=user, game_id=game, score=score))
            db.commit()

    def abandon(self, entry, when):
        with database.SessionLocal() as db:
            db.get(models.UserGame, entry).abandoned_at = when
            db.commit()

    def test_it_needs_a_login_and_an_empty_group_has_empty_lists(self):
        self.assertEqual(self.api("GET", "/group/library").status_code, 401)
        body = self.library().json()
        self.assertEqual(body["summary"], {"games": 0, "players": 0, "played_seconds": 0})
        self.assertEqual((body["hidden_gems"], body["graveyard"], body["genres"], body["platforms"]), ([], [], [], []))
        self.assertEqual((body["rarities"], body["untouched"]), ({"total": 0, "items": []}, {"total": 0, "items": []}))

    def test_the_summary_counts_distinct_games_players_and_hours_and_never_the_emergency_account(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "switch")
        self.library_entry(self.god, "doom", TODAY(), "pc")
        self.session(self.ana, "celeste", ago(hours=3), 90)
        body = self.library().json()
        self.assertEqual(body["summary"], {"games": 1, "players": 2, "played_seconds": 5400})

    def test_hidden_gems_are_few_owners_and_well_rated(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "pc")
        self.library_entry(self.cai, "celeste", TODAY(), "pc")
        self.library_entry(self.ana, "doom", TODAY(), "pc")
        self.rate(self.ana, "hades", 95)
        self.rate(self.ana, "celeste", 99)  # three owners: not hidden
        self.rate(self.ana, "doom", 50)  # badly rated
        body = self.library().json()
        [gem] = body["hidden_gems"]
        self.assertEqual((gem["game_id"], gem["game_name"], gem["players"], gem["score_mean"], gem["score_count"]), ("hades", "Hades", 1, 95.0, 1))

    def test_the_graveyard_lists_games_given_up_and_not_gone_back_to(self):
        gave_up = self.library_entry(self.ana, "doom", TODAY(), "pc")
        self.library_entry(self.bea, "doom", TODAY(), "pc")
        self.session(self.ana, "doom", ago(hours=30), 20)
        self.abandon(gave_up, clock.now() - datetime.timedelta(hours=10))
        resumed = self.library_entry(self.bea, "hades", TODAY(), "pc")
        self.session(self.bea, "hades", ago(hours=2), 20)
        self.abandon(resumed, clock.now() - datetime.timedelta(hours=10))  # played again after the mark: not abandoned
        finished = self.library_entry(self.ana, "limbo", TODAY(), "pc", completed=1, completed_date=TODAY())
        self.abandon(finished, clock.now() - datetime.timedelta(hours=10))  # completed: never abandoned
        body = self.library().json()
        self.assertEqual([(g["game_id"], g["abandoned_by"], g["players"]) for g in body["graveyard"]], [("doom", ["Ana"], 2)])

    def test_a_game_completed_on_another_platform_that_season_is_not_abandoned(self):
        gave_up = self.library_entry(self.ana, "doom", TODAY(), "pc")
        self.library_entry(self.ana, "doom", TODAY(), "switch", completed=1, completed_date=TODAY())
        self.abandon(gave_up, clock.now() - datetime.timedelta(hours=10))
        self.assertEqual(self.library().json()["graveyard"], [])

    def test_rarities_have_one_owner_and_untouched_games_have_no_session(self):
        self.library_entry(self.ana, "doom", TODAY(), "pc")
        self.session(self.ana, "doom", ago(hours=3), 30)
        self.library_entry(self.ana, "tetris", TODAY(), "pc")  # one owner, never played
        self.library_entry(self.ana, "limbo", TODAY(), "pc")
        self.library_entry(self.bea, "limbo", TODAY(), "pc")  # two owners, never played
        body = self.library().json()
        self.assertEqual(body["rarities"]["total"], 2)
        self.assertEqual([(g["game_id"], g["owner"], g["seconds"]) for g in body["rarities"]["items"]], [("doom", "Ana", 1800), ("tetris", "Ana", 0)])
        self.assertEqual(body["untouched"]["total"], 2)
        self.assertEqual([(g["game_id"], g["players"]) for g in body["untouched"]["items"]], [("limbo", 2), ("tetris", 1)])

    def test_the_coverage_by_genre_and_platform(self):
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.library_entry(self.bea, "celeste", TODAY(), "switch")
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.session(self.ana, "hades", ago(hours=3), 60)
        body = self.library().json()
        genres = {g["genre"]: g for g in body["genres"]}
        self.assertEqual((genres["Indie"]["games"], genres["Indie"]["players"], genres["Indie"]["seconds"]), (2, 2, 3600))
        self.assertEqual(genres["Roguelike"]["games"], 1)
        platforms = {p["platform"]: p for p in body["platforms"]}
        self.assertEqual((platforms["pc"]["games"], platforms["pc"]["players"], platforms["pc"]["platform_name"]), (2, 1, "PC"))
        self.assertEqual((platforms["switch"]["games"], platforms["switch"]["players"]), (1, 1))

    def test_the_lists_are_cut_to_ten_but_the_total_is_kept(self):
        for n in range(12):
            self.game(f"g{n}", f"Juego {n}")
            self.library_entry(self.ana, f"g{n}", TODAY(), "pc")
        body = self.library().json()
        self.assertEqual((body["rarities"]["total"], len(body["rarities"]["items"])), (12, 10))
        self.assertEqual((body["untouched"]["total"], len(body["untouched"]["items"])), (12, 10))
