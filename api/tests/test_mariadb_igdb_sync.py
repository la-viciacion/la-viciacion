"""The link of the catalogue to IGDB (MariaDB required, see api_support.py). IGDB is a fake, the throttling sleeps are
skipped and the background thread runs in the test, so a whole run is one call to `start()` and a look at `status()`."""
import datetime
import unittest
from types import SimpleNamespace
from unittest import mock

from src.clients import igdb
from src.database import database, models
from src.utils import igdb_sync
from tests.api_support import ApiTestCase


def stamp(year):
    return int(datetime.datetime(year, 6, 1, tzinfo=datetime.timezone.utc).timestamp())


def item(igdb_id, name, year=None, game_type=0, version_parent=None):
    return {"id": igdb_id, "name": name, "slug": name.lower().replace(" ", "-"), "first_release_date": stamp(year) if year else None, "game_type": game_type,
            "version_parent": version_parent, "platforms": [{"name": "PC"}],
            "themes": [{"name": "Fantasy"}], "keywords": [{"name": "Roguelike"}], "franchises": [{"name": f"Saga of {name}"}]}


def game(name, year=None, steam=None):
    return SimpleNamespace(name=name, release_date=datetime.date(year, 1, 1) if year else None, steam_id=steam)


class ChooseTests(unittest.TestCase):
    """The decision of what to do with a game is pure: no database is read."""

    def test_the_steam_app_decides_when_it_points_at_one_game(self):
        verdict, found = igdb_sync.choose(game("Hades II", 2024, steam="1145350"), [item(5, "Hades II", 2025)], [])
        self.assertEqual((verdict, found["id"]), ("linked", 5))

    def test_a_steam_app_shared_by_a_game_and_its_edition_picks_the_game(self):
        hits = [item(1, "Horizon Zero Dawn: Complete Edition", 2020, game_type=3, version_parent=2), item(2, "Horizon Zero Dawn", 2017)]
        self.assertEqual(igdb_sync.choose(game("Horizon Zero Dawn", steam="1"), hits, [])[1]["id"], 2)

    def test_a_steam_app_with_two_games_proper_is_left_to_a_human(self):
        verdict, found = igdb_sync.choose(game("X", steam="1"), [item(1, "X", 2000), item(2, "X HD", 2010)], [])
        self.assertEqual((verdict, [c["id"] for c in found]), ("ambiguous", [1, 2]))

    def test_the_same_name_and_a_year_that_agrees_links_it_roman_numerals_included(self):
        verdict, found = igdb_sync.choose(game("Alan Wake 2", 2023), [], [item(7, "Alan Wake II", 2023)])
        self.assertEqual((verdict, found["id"]), ("linked", 7))
        self.assertEqual(igdb_sync.choose(game("Outlast", 2013), [], [item(8, "Outlast", 2014)])[0], "linked")  # a year of margin

    def test_a_game_that_came_out_in_early_access_is_recognised_by_the_year_of_its_early_access(self):
        launch = item(1, "Valheim", 2026)
        launch["release_dates"] = [{"date": stamp(2021), "date_format": 0, "status": {"name": "Early Access"}}, {"date": stamp(2026), "date_format": 0}]
        verdict, found = igdb_sync.choose(game("Valheim", 2021), [], [launch])
        self.assertEqual((verdict, found["id"]), ("linked", 1))
        self.assertEqual(igdb_sync.choose(game("Valheim", 2021), [], [item(1, "Valheim", 2026)])[0], "ambiguous")  # no early access listed: a human decides

    def test_a_remake_is_not_the_original(self):
        names = [item(1, "Resident Evil 4", 2005), item(2, "Resident Evil 4", 2023, game_type=8)]
        self.assertEqual(igdb_sync.choose(game("Resident Evil 4", 2023), [], names)[1]["id"], 2)
        verdict, found = igdb_sync.choose(game("Silent Hill 2", 2024), [], [item(3, "Silent Hill 2", 2001)])
        self.assertEqual((verdict, [c["id"] for c in found]), ("ambiguous", [3]))  # the name is right and the year is not

    def test_a_game_without_a_year_links_only_when_one_entry_has_its_name(self):
        self.assertEqual(igdb_sync.choose(game("Celeste"), [], [item(1, "Celeste", 2018)])[0], "linked")
        self.assertEqual(igdb_sync.choose(game("Celeste"), [], [item(1, "Celeste", 2018), item(2, "Celeste", 2019)])[0], "ambiguous")

    def test_a_name_that_is_not_exact_is_never_linked_and_nothing_is_not_found(self):
        verdict, found = igdb_sync.choose(game("Fear", 2017), [], [item(1, "Layers of Fear", 2016)])
        self.assertEqual((verdict, found[0]["id"]), ("ambiguous", 1))
        self.assertEqual(igdb_sync.choose(game("Nothing"), [], []), ("not_found", None))


class SameThread:
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class IgdbSyncRunTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        igdb_sync._status.clear()
        igdb_sync._status["state"] = "idle"
        igdb_sync._cancel.clear()
        self.by_steam, self.by_name, self.asked, self.extras, self.details = {}, {}, [], {}, {}
        for patcher in (
            mock.patch.object(igdb_sync.time, "sleep"),
            mock.patch.object(igdb_sync.threading, "Thread", new=SameThread),
            mock.patch.object(igdb, "configured", return_value=True),
            mock.patch.object(igdb, "find_by_steam", side_effect=lambda steam: self.by_steam.get(steam, [])),
            mock.patch.object(igdb, "search_items", side_effect=self.search),
            mock.patch.object(igdb, "game_extras", side_effect=lambda igdb_id: self.extras.get(igdb_id)),
            mock.patch.object(igdb, "game_details", side_effect=lambda igdb_id: self.details.get(igdb_id)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def search(self, name, limit=10, extras=False):
        self.asked.append(name)
        answer = self.by_name.get(name)
        if isinstance(answer, Exception):
            raise answer
        return answer or []

    def igdb_id(self, game_id):
        with database.SessionLocal() as db:
            return db.get(models.Game, game_id).igdb_id

    def igdb_slug(self, game_id):
        with database.SessionLocal() as db:
            return db.get(models.Game, game_id).igdb_slug

    def igdb_data(self, game_id):
        with database.SessionLocal() as db:
            g = db.get(models.Game, game_id)
            return g.themes, g.keywords, g.franchises, g.collections

    def run_sync(self, max_games=None, overwrite=False):
        self.assertTrue(igdb_sync.start(max_games, overwrite))
        return igdb_sync.status()

    def test_certain_matches_are_linked_and_the_rest_is_listed_without_touching_anything_else(self):
        self.game("hades", "Hades", steam_id="1145350", dev="Me")
        self.game("celeste", "Celeste", release_date=datetime.date(2018, 1, 25))
        self.game("fear", "Fear", release_date=datetime.date(2017, 1, 1))
        self.game("ghost", "Ghost")
        self.by_steam["1145350"] = [item(10, "Hades II", 2025)]
        self.by_name.update({"Celeste": [item(20, "Celeste", 2018)], "Fear": [item(30, "Layers of Fear", 2016)]})
        status = self.run_sync()
        self.assertEqual((status["state"], status["stop_reason"], status["linked"], status["processed"]), ("finished", "completed", 2, 4))
        self.assertEqual([self.igdb_id(g) for g in ("hades", "celeste", "fear", "ghost")], [10, 20, None, None])
        self.assertEqual([a["name"] for a in status["ambiguous"]], ["Fear"])
        self.assertEqual(status["ambiguous"][0]["candidates"][0]["igdb_id"], 30)
        self.assertEqual([n["name"] for n in status["not_found"]], ["Ghost"])
        with database.SessionLocal() as db:
            self.assertEqual(db.get(models.Game, "hades").dev, "Me")

    def igdb_details(self, igdb_id, name, **fields):
        return {
            "igdb_id": igdb_id, "name": name, "slug": "x", "igdb_slug": f"{name.lower()}-igdb", "dev": "IGDB Studio", "steam_id": "", "release_date": datetime.date(2018, 1, 25),
            "image_url": "https://images.igdb.com/cover.jpg", "genres": "Platform", "is_dlc": False, "parent_igdb_id": None,
            "themes": "Fantasy", "keywords": "Roguelike", "franchises": "", "collections": "", **fields,
        }

    def test_with_overwrite_a_game_that_is_linked_takes_igdbs_data_and_without_it_keeps_its_own(self):
        for name, game_id in (("Celeste", "celeste"), ("Hades", "hades")):
            self.game(game_id, name, release_date=datetime.date(2018, 1, 25), dev="RAWG Studio", image_url="https://media.rawg.io/old.jpg", genres="Platformer", rawg_id=1)
        self.by_name.update({"Celeste": [item(20, "Celeste", 2018)], "Hades": [item(21, "Hades", 2018)]})
        self.details[20] = self.igdb_details(20, "Celeste")
        self.details[21] = self.igdb_details(21, "Hades")
        with database.SessionLocal() as db:
            db.get(models.Game, "hades").image_url = "https://media.rawg.io/hades.jpg"
            db.commit()
        self.run_sync(max_games=1, overwrite=True)  # alphabetical: Celeste only
        with database.SessionLocal() as db:
            celeste, hades = db.get(models.Game, "celeste"), db.get(models.Game, "hades")
            self.assertEqual((celeste.dev, celeste.image_url, celeste.genres, celeste.igdb_id), ("IGDB Studio", "https://images.igdb.com/cover.jpg", "Platform", 20))
            self.assertEqual((hades.dev, hades.genres, hades.igdb_id), ("RAWG Studio", "Platformer", None))  # not in the batch
        igdb_sync._status["state"] = "idle"
        self.run_sync(overwrite=False)  # Hades, linked without replacing
        with database.SessionLocal() as db:
            hades = db.get(models.Game, "hades")
            self.assertEqual((hades.igdb_id, hades.dev, hades.image_url, hades.genres), (21, "RAWG Studio", "https://media.rawg.io/hades.jpg", "Platformer"))

    def test_with_overwrite_a_game_linked_but_incomplete_is_replaced_too_and_a_complete_one_is_not_touched(self):
        self.game("old", "Old", igdb_id=50, dev="RAWG Studio", genres="Platformer")
        self.game("done", "Done", igdb_id=51, igdb_slug="done", themes="", keywords="", franchises="", collections="", perspectives="", game_modes="", dev="Keep")
        self.details[50] = self.igdb_details(50, "Old")
        status = self.run_sync(overwrite=True)
        self.assertEqual((status["filled"], status["total"]), (1, 1))
        with database.SessionLocal() as db:
            self.assertEqual((db.get(models.Game, "old").dev, db.get(models.Game, "old").genres, db.get(models.Game, "done").dev), ("IGDB Studio", "Platform", "Keep"))

    def test_a_game_is_linked_on_the_spot_when_there_is_a_certain_match_and_otherwise_left_alone(self):
        self.game("celeste", "Celeste", release_date=datetime.date(2018, 1, 25), dev="Keep")
        self.game("fear", "Fear", release_date=datetime.date(2017, 1, 1))
        self.game("dup", "Celeste Classic", release_date=datetime.date(2018, 1, 1))
        self.game("owner", "Owner", igdb_id=22, igdb_slug="owner", themes="", perspectives="")
        self.by_name.update({"Celeste": [item(20, "Celeste", 2018)], "Fear": [item(30, "Layers of Fear", 2016)], "Celeste Classic": [item(22, "Celeste Classic", 2018)]})
        with database.SessionLocal() as db:
            games = {g.id: g for g in db.query(models.Game)}
            self.assertEqual([igdb_sync.link_one(db, games[g]) for g in ("celeste", "fear", "dup", "owner")], [True, False, False, False])
            self.assertEqual((games["celeste"].igdb_id, games["celeste"].igdb_slug, games["celeste"].themes, games["celeste"].dev), (20, "celeste", "Fantasy", "Keep"))
            self.assertEqual((games["fear"].igdb_id, games["dup"].igdb_id), (None, None))
        with mock.patch.object(igdb, "configured", return_value=False), database.SessionLocal() as db:
            self.assertFalse(igdb_sync.link_one(db, db.get(models.Game, "fear")))

    def test_a_linked_game_gets_what_igdb_says_of_it(self):
        self.game("celeste", "Celeste", release_date=datetime.date(2018, 1, 25))
        self.by_name["Celeste"] = [item(20, "Celeste", 2018)]
        self.run_sync()
        self.assertEqual(self.igdb_data("celeste"), ("Fantasy", "Roguelike", "Saga of Celeste", ""))
        self.assertEqual(self.igdb_slug("celeste"), "celeste")

    def test_a_linked_game_without_the_address_of_its_igdb_page_is_asked_for_it(self):
        self.game("old", "Old", igdb_id=50, themes="", keywords="", franchises="", collections="")  # linked before igdb_slug
        self.extras[50] = {"themes": "", "keywords": "", "franchises": "", "collections": "", "igdb_slug": "old-game"}
        self.assertEqual((self.run_sync()["filled"], self.igdb_slug("old")), (1, "old-game"))

    def test_a_game_already_linked_but_without_igdb_data_is_filled_and_one_with_it_is_left_alone(self):
        self.game("hades", "Hades", igdb_id=10, igdb_slug="hades")
        self.game("done", "Done", igdb_id=11, igdb_slug="done", themes="Horror", keywords="", franchises="", collections="", perspectives="", game_modes="")
        self.extras[10] = {"themes": "Fantasy", "keywords": "Roguelike", "franchises": "", "collections": "Hades", "igdb_slug": "hades-slug"}
        status = self.run_sync()
        self.assertEqual((status["filled"], status["linked"], status["processed"], self.asked), (1, 0, 1, []))
        self.assertEqual(self.igdb_data("hades"), ("Fantasy", "Roguelike", "", "Hades"))
        self.assertEqual(self.igdb_slug("hades"), "hades-slug")
        self.assertEqual(self.igdb_data("done"), ("Horror", "", "", ""))
        self.game("gone", "Gone", igdb_id=12)  # IGDB no longer has it
        igdb_sync._status["state"] = "idle"
        self.assertEqual([n["name"] for n in self.run_sync()["not_found"]], ["Gone"])

    def test_a_batch_takes_the_first_games_alphabetically_and_a_game_already_linked_is_not_asked(self):
        for game_id, name in (("a", "Alpha"), ("b", "Beta"), ("c", "Gamma"), ("d", "Delta")):
            self.game(game_id, name)
        self.game("done", "Aaa Done", igdb_id=1, igdb_slug="done", themes="", perspectives="")
        self.by_name.update({"Alpha": [item(11, "Alpha")], "Beta": [item(12, "Beta")]})
        status = self.run_sync(max_games=2)
        self.assertEqual((status["total"], status["linked"], self.asked), (2, 2, ["Alpha", "Beta"]))
        self.assertEqual(self.igdb_id("done"), 1)

    def test_an_igdb_id_another_game_has_is_a_duplicate_and_is_not_assigned(self):
        self.game("one", "Celeste", igdb_id=20, igdb_slug="celeste")
        self.game("two", "Celeste Classic", release_date=datetime.date(2018, 1, 1))
        self.by_name["Celeste Classic"] = [item(20, "Celeste Classic", 2018)]
        status = self.run_sync()
        self.assertEqual((status["linked"], status["duplicates"][0]["other_name"]), (0, "Celeste"))
        self.assertIsNone(self.igdb_id("two"))

    def test_five_failures_in_a_row_stop_the_run_and_a_refusal_stops_it_at_once(self):
        for n in range(7):
            self.game(f"g{n}", f"Game {n}")
            self.by_name[f"Game {n}"] = igdb.IgdbError("IGDB did not answer")
        status = self.run_sync()
        self.assertEqual((status["stop_reason"], len(status["errors"])), ("errors", 5))
        igdb_sync._status["state"] = "idle"
        self.by_name = {f"Game {n}": igdb.IgdbRefused("Twitch refused the credentials (403)") for n in range(7)}
        self.assertTrue(igdb_sync.start(None))
        self.assertIn("refused the credentials", igdb_sync.status()["stop_reason"])

    def test_without_credentials_it_does_not_start(self):
        with mock.patch.object(igdb, "configured", return_value=False):
            with self.assertRaises(RuntimeError):
                igdb_sync.start()

    def test_the_estimate_counts_the_games_without_an_id_or_without_igdb_data(self):
        self.game("a", "A")
        self.game("b", "B", igdb_id=2)  # linked, its data never asked
        self.game("c", "C", igdb_id=3, igdb_slug="c", themes="", perspectives="")
        with database.SessionLocal() as db:
            self.assertEqual(
                (igdb_sync.estimate(db)["pending_games"], igdb_sync.estimate(db, 1)["games"], igdb_sync.estimate(db)["total_games"]),
                (2, 1, 3),
            )

    def test_the_dates_of_the_wished_games_are_refreshed_from_igdb_and_what_it_cannot_say_goes_elsewhere(self):
        old = datetime.date(2026, 1, 1)
        self.game("a", "A", igdb_id=1, release_date=old)
        self.game("b", "B", igdb_id=2, release_date=old)
        self.game("c", "C", rawg_id=3, release_date=old)  # IGDB does not know it
        with database.SessionLocal() as db:
            games = [db.get(models.Game, g) for g in ("a", "b", "c")]
            with mock.patch.object(igdb, "release_dates", return_value={1: datetime.date(2026, 9, 15)}):
                changed, unanswered = igdb_sync.refresh_release_dates(db, games)
            self.assertEqual(([g.id for g in changed], [g.id for g in unanswered]), (["a"], ["c"]))  # B: IGDB has no exact day, so it stays
            self.assertEqual((games[0].release_date, games[1].release_date), (datetime.date(2026, 9, 15), old))
            with mock.patch.object(igdb, "release_dates", side_effect=igdb.IgdbError("down")):
                changed, unanswered = igdb_sync.refresh_release_dates(db, games)
            self.assertEqual(([g.id for g in changed], sorted(g.id for g in unanswered)), ([], ["a", "b", "c"]))
        with mock.patch.object(igdb, "configured", return_value=False):
            self.assertEqual(igdb_sync.refresh_release_dates(None, games), ([], games))

    def test_a_doubtful_game_is_linked_by_hand_once_igdb_has_it(self):
        self.game("fear", "Fear")
        self.game("other", "Other", igdb_id=30, igdb_slug="other")
        with database.SessionLocal() as db, mock.patch.object(igdb, "game_details", return_value={"name": "Fear", "themes": "Horror", "keywords": "", "franchises": "", "collections": ""}):
            self.assertEqual(igdb_sync.apply_one(db, "fear", 31), {"linked": True, "changed": ["igdb_id"]})
            self.assertEqual(db.get(models.Game, "fear").themes, "Horror")
            with self.assertRaises(ValueError):
                igdb_sync.apply_one(db, "fear", 30)
            with self.assertRaises(LookupError):
                igdb_sync.apply_one(db, "nope", 32)
        with database.SessionLocal() as db, mock.patch.object(igdb, "game_details", return_value=None):
            with self.assertRaises(LookupError):
                igdb_sync.apply_one(db, "other", 99)
        self.assertEqual(self.igdb_id("fear"), 31)
