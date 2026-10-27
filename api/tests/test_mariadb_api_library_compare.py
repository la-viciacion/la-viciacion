"""The game page's pace and the comparison of two libraries through real requests (MariaDB required, see
api_support.py)."""
from src.database import database, models
from tests import clock
from tests.api_support import ApiTestCase
from tests.clock import ago

TODAY = clock.today


class CompareTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.bea = self.user("bea")
        self.cai = self.user("cai")
        self.root = self.user("admin", admin=True)  # the emergency account (models.GOD_USERNAME)
        for game_id, name in (("celeste", "Celeste"), ("hades", "Hades"), ("tetris", "Tetris"), ("doom", "Doom"), ("limbo", "Limbo")):
            self.game(game_id, name)

    def have(self, user, game, minutes=0, completed=False, score=None):
        self.library_entry(user, game, TODAY(), "pc", **({"completed": 1, "completed_date": TODAY()} if completed else {}))
        if minutes:
            self.session(user, game, ago(hours=3), minutes)
        if score is not None:
            with database.SessionLocal() as db:
                db.add(models.GameScore(user_id=user, game_id=game, score=score))
                db.commit()


class CompareTests(CompareTestCase):
    def compare(self, player, as_user="ana"):
        return self.api("GET", f"/group/players/{player}/compare", as_user=as_user)

    def test_it_splits_the_games_with_the_hours_completions_and_ratings_of_each(self):
        self.have(self.ana, "celeste", 120, completed=True, score=90)
        self.have(self.ana, "hades", 30)
        self.have(self.ana, "tetris", 10)
        self.have(self.bea, "celeste", 60, score=70)
        self.have(self.bea, "doom", 200)
        body = self.compare(self.bea).json()
        self.assertEqual(body["player"], {"id": self.bea, "name": "Bea"})
        self.assertEqual(body["counts"], {"shared": 1, "only_mine": 2, "only_theirs": 1})
        shared = body["shared"][0]
        self.assertEqual((shared["game_id"], shared["game_name"]), ("celeste", "Celeste"))
        self.assertEqual(shared["mine"], {"seconds": 7200, "completed": True, "score": 90})
        self.assertEqual(shared["theirs"], {"seconds": 3600, "completed": False, "score": 70})
        self.assertEqual([g["game_id"] for g in body["only_mine"]], ["hades", "tetris"])  # the most played first
        self.assertEqual((body["only_mine"][0]["theirs"], body["only_theirs"][0]["game_id"], body["only_theirs"][0]["mine"]), (None, "doom", None))
        self.assertIn("percent", body["affinity"])

    def test_the_other_side_is_the_mirror(self):
        self.have(self.ana, "hades", 30)
        self.have(self.bea, "doom", 200)
        body = self.compare(self.ana, as_user="bea").json()
        self.assertEqual(([g["game_id"] for g in body["only_mine"]], [g["game_id"] for g in body["only_theirs"]]), (["doom"], ["hades"]))

    def test_nothing_in_common_and_an_empty_library_are_fine(self):
        body = self.compare(self.cai).json()
        self.assertEqual((body["counts"], body["shared"], body["only_mine"], body["only_theirs"]), ({"shared": 0, "only_mine": 0, "only_theirs": 0}, [], [], []))
        self.assertIsNone(body["affinity"]["percent"])

    def test_a_game_on_several_seasons_or_platforms_counts_once_with_all_its_time(self):
        self.library_entry(self.ana, "hades", TODAY(), "pc")
        self.library_entry(self.ana, "hades", TODAY().replace(year=TODAY().year - 1), "switch")
        self.session(self.ana, "hades", ago(hours=3), 30)
        self.session(self.ana, "hades", ago(hours=9), 30)
        self.have(self.bea, "hades", 10)
        body = self.compare(self.bea).json()
        self.assertEqual((body["counts"]["shared"], body["shared"][0]["mine"]["seconds"]), (1, 3600))

    def test_one_cannot_compare_with_oneself_and_the_player_must_exist(self):
        self.assertEqual(self.compare(self.ana).status_code, 400)
        self.assertEqual(self.compare(99999).status_code, 404)
        self.assertEqual(self.compare(self.root).status_code, 404)  # the emergency account is not a player

    def test_a_login_is_needed(self):
        self.assertEqual(self.api("GET", f"/group/players/{self.bea}/compare").status_code, 401)


class PaceTests(CompareTestCase):
    def setUp(self):
        super().setUp()
        with database.SessionLocal() as db:
            db.query(models.Game).filter_by(id="celeste").update({"avg_time": 14400})
            db.commit()

    def pace(self, as_user="ana"):
        return self.api("GET", "/games/celeste/overview", as_user=as_user).json()["pace"]

    def test_it_compares_with_those_who_completed_it_and_with_the_average(self):
        self.have(self.ana, "celeste", 180, completed=True)
        self.have(self.bea, "celeste", 120, completed=True)
        self.have(self.cai, "celeste", 600)  # has not completed it: not part of the group's time
        pace = self.pace()
        self.assertEqual((pace["seconds"], pace["completed"], pace["group_mean"], pace["group_count"]), (10800, True, 7200, 1))
        self.assertEqual((pace["group_share"], pace["avg_time"], pace["avg_share"]), (150, 14400, 75))

    def test_it_is_for_the_viewer_who_has_played_it_only(self):
        self.have(self.bea, "celeste", 120, completed=True)
        self.assertIsNone(self.pace())  # ana does not have it
        self.library_entry(self.ana, "celeste", TODAY(), "pc")
        self.assertIsNone(self.pace())  # she has it, but has not played it
        self.assertEqual(self.pace(as_user="bea")["group_count"], 0)  # nobody else completed it

    def test_a_game_without_average_time_compares_only_with_the_group(self):
        self.have(self.ana, "hades", 60)
        self.have(self.bea, "hades", 30, completed=True)
        pace = self.api("GET", "/games/hades/overview", as_user="ana").json()["pace"]
        self.assertEqual((pace["avg_time"], pace["avg_share"], pace["group_share"]), (None, None, 200))
