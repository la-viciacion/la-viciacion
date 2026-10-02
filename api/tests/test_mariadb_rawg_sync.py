"""The bulk sync of the catalogue against RAWG (MariaDB required, see api_support.py). RAWG is a fake that routes
by path and counts every call, the throttling sleeps are skipped and the background thread runs in the test, so
a whole sync is one deterministic call to `start()` followed by a look at `status()`."""
import datetime
from unittest import mock

import requests

from src.database import database, models
from src.utils import rawg_sync
from tests.api_support import ApiTestCase

KEY = "secret-rawg-key-1234"


class Resp:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code = payload or {}, status
        self.ok = status < 400

    def json(self):
        return self.payload


class FakeRawg:
    """Answers /games (search), /games/{id} and /games/{id}/stores from dicts; unknown ids are 404."""

    def __init__(self):
        self.search_results: dict[str, list] = {}
        self.details: dict[int, dict] = {}
        self.stores: dict[int, list] = {}
        self.status_for: dict[str, list] = {}  # path -> statuses to answer with, one per call, then normal
        self.calls: list[str] = []
        self.error_for: dict[str, Exception] = {}

    def __call__(self, url, params=None, timeout=None):
        path = url.removeprefix("https://api.rawg.io/api")
        self.calls.append(path)
        assert params["key"] == KEY, "the key must travel as a parameter"
        if path in self.error_for:
            raise self.error_for[path]
        queued = self.status_for.get(path)
        if queued:
            status = queued.pop(0)
            if status != 200:
                return Resp(status=status)
        if path == "/games":
            return Resp({"results": self.search_results.get(params["search"].lower(), [])})
        parts = path.strip("/").split("/")
        rawg_id = int(parts[1])
        if len(parts) == 3:
            return Resp({"results": self.stores.get(rawg_id, [])})
        return Resp(self.details[rawg_id]) if rawg_id in self.details else Resp(status=404)


def rawg_game(rawg_id, name, slug=None, **extra):
    return {"id": rawg_id, "name": name, "slug": slug or name.lower().replace(" ", "-"), "released": "2018-01-25",
            "background_image": f"https://img/{rawg_id}.jpg", "genres": [{"name": "Indie"}, {"name": "Platformer"}],
            "developers": [{"name": "Maddy Makes Games"}], "publishers": [{"name": "Publisher Co"}], **extra}


class SyncTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.rawg = FakeRawg()
        rawg_sync._status.clear()
        rawg_sync._status["state"] = "idle"
        rawg_sync._cancel.clear()

        class SameThread:
            """Runs the sync inside `start()`, so the test sees the finished status."""

            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        for patcher in (
            mock.patch.object(type(rawg_sync.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=KEY),
            mock.patch.object(rawg_sync.requests, "get", new=self.rawg),
            mock.patch.object(rawg_sync.time, "sleep"),
            mock.patch.object(rawg_sync.threading, "Thread", new=SameThread),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def sync(self, max_calls=1000, overwrite=False):
        self.assertTrue(rawg_sync.start(max_calls, overwrite))
        return rawg_sync.status()

    def game_row(self, game_id):
        with database.SessionLocal() as db:
            return db.get(models.Game, game_id)


class PureHelpersTests(ApiTestCase):
    def test_names_are_compared_ignoring_case_punctuation_and_a_leading_the(self):
        self.assertEqual(rawg_sync._norm("The Witcher 3: Wild Hunt"), rawg_sync._norm("witcher 3 - wild hunt!"))
        self.assertEqual(rawg_sync._norm(None), "")
        self.assertNotEqual(rawg_sync._norm("Hades"), rawg_sync._norm("Hades II"))

    def test_a_blank_value_is_none_empty_or_a_dash(self):
        for blank in (None, "", "  ", "-", " - "):
            self.assertTrue(rawg_sync._blank(blank), repr(blank))
        for filled in ("x", 0, "0"):
            self.assertFalse(rawg_sync._blank(filled), repr(filled))

    def test_a_result_is_trusted_only_when_the_name_or_the_slug_matches_exactly(self):
        game = models.Game(id="g", name="The Legend of Zelda", slug="zelda-legend")
        results = [{"id": 1, "name": "Zelda II", "slug": "zelda-2"}, {"id": 2, "name": "Legend of Zelda", "slug": "x"}]
        self.assertEqual(rawg_sync._pick_confident(game, results)["id"], 2)
        by_slug = [{"id": 3, "name": "Something else", "slug": "zelda-legend"}]
        self.assertEqual(rawg_sync._pick_confident(game, by_slug)["id"], 3)
        self.assertIsNone(rawg_sync._pick_confident(game, [{"id": 4, "name": "Zelda: Link", "slug": "link"}]))
        self.assertIsNone(rawg_sync._pick_confident(models.Game(id="g", name="Hades"), []))

    def test_a_candidate_for_the_panel_keeps_four_platforms_at_most(self):
        item = {"id": 5, "name": "N", "released": "2020-01-01", "platforms": [{"platform": {"name": f"P{n}"}} for n in range(6)] + [{}]}
        self.assertEqual(rawg_sync._candidate(item)["platforms"], ["P0", "P1", "P2", "P3"])

    def test_applying_fills_blanks_never_blanks_a_value_and_overwrites_only_when_asked(self):
        game = models.Game(id="g", name="G", dev="Old Dev", slug=None, genres="", steam_id="-", image_url="https://old", rawg_id=None)
        det = {"rawg_id": 7, "slug": "g", "dev": "New Dev", "release_date": datetime.date(2020, 1, 1), "image_url": "https://new",
               "genres": "RPG", "steam_id": ""}
        changed = rawg_sync._apply(game, det, overwrite=False)
        self.assertEqual(sorted(changed), ["genres", "rawg_id", "release_date", "slug"])
        self.assertEqual((game.dev, game.image_url, game.steam_id), ("Old Dev", "https://old", "-"))  # kept: not blank / nothing to put
        overwritten = rawg_sync._apply(game, det, overwrite=True)
        self.assertEqual(sorted(overwritten), ["dev", "image_url"])
        self.assertEqual(game.steam_id, "-")  # an empty answer never blanks a value


class ClientTests(SyncTestCase):
    def rawg_client(self, max_calls=10):
        return rawg_sync._Client(max_calls)

    def test_every_request_counts_against_the_budget(self):
        self.rawg.details[1] = rawg_game(1, "A")
        client = self.rawg_client(2)
        client.get("/games/1")
        self.assertTrue(client.budget_left(1))
        client.get("/games/1")
        self.assertEqual((client.calls, client.budget_left(1)), (2, False))

    def test_a_transient_upstream_error_is_retried_once_and_both_tries_count(self):
        self.rawg.details[1] = rawg_game(1, "A")
        self.rawg.status_for["/games/1"] = [502, 200]
        client = self.rawg_client()
        self.assertEqual(client.get("/games/1")["id"], 1)
        self.assertEqual(client.calls, 2)

    def test_it_does_not_retry_when_the_budget_is_spent(self):
        self.rawg.status_for["/games/1"] = [503, 200]
        client = self.rawg_client(1)
        with self.assertRaises(ConnectionError):
            client.get("/games/1")
        self.assertEqual(client.calls, 1)

    def test_a_key_or_quota_problem_aborts_with_a_clear_reason(self):
        for status in (401, 403, 429):
            self.rawg.status_for["/games/1"] = [status]
            with self.assertRaisesRegex(rawg_sync.RawgFatal, str(status)):
                self.rawg_client().get("/games/1")

    def test_other_failures_are_connection_errors_without_the_key(self):
        with self.assertRaises(ConnectionError) as caught:
            self.rawg_client().get("/games/404")
        self.assertIn("404", str(caught.exception))
        self.rawg.error_for["/games/9"] = requests.ConnectionError(f"failed for key={KEY}")
        with self.assertRaises(ConnectionError) as network:
            self.rawg_client().get("/games/9")
        self.assertNotIn(KEY, str(network.exception))

    def test_the_details_are_parsed_and_the_steam_id_is_found_in_the_stores(self):
        self.rawg.details[1] = rawg_game(1, "Celeste")
        self.rawg.stores[1] = [{"url": "https://store.epicgames.com/x"}, {"url": "https://store.steampowered.com/app/504230/Celeste/"}]
        details = rawg_sync._details(self.rawg_client(), 1, need_steam=True)
        self.assertEqual((details["dev"], details["genres"], details["steam_id"], details["release_date"]),
                         ("Maddy Makes Games", "Indie,Platformer", "504230", datetime.date(2018, 1, 25)))

    def test_the_publishers_stand_in_for_missing_developers_and_a_bad_date_is_dropped(self):
        self.rawg.details[1] = rawg_game(1, "Celeste", developers=[], released="soon")
        details = rawg_sync._details(self.rawg_client(), 1, need_steam=False)
        self.assertEqual((details["dev"], details["release_date"], details["steam_id"]), ("Publisher Co", None, ""))
        self.assertNotIn("/games/1/stores", self.rawg.calls)  # not asked for when not needed

    def test_a_failing_stores_lookup_is_best_effort(self):
        self.rawg.details[1] = rawg_game(1, "Celeste")
        self.rawg.status_for["/games/1/stores"] = [500, 500]
        self.assertEqual(rawg_sync._details(self.rawg_client(), 1, need_steam=True)["steam_id"], "")


class SyncRunTests(SyncTestCase):
    def test_a_game_without_rawg_id_is_matched_by_name_and_filled(self):
        self.game("celeste", "Celeste")
        self.rawg.search_results["celeste"] = [rawg_game(101, "Celeste")]
        self.rawg.details[101] = rawg_game(101, "Celeste")
        status = self.sync()
        self.assertEqual((status["state"], status["stop_reason"], status["updated"], status["processed"], status["total"]), ("finished", "completed", 1, 1, 1))
        game = self.game_row("celeste")
        self.assertEqual((game.rawg_id, game.slug, game.dev, game.genres, game.name), (101, "celeste", "Maddy Makes Games", "Indie,Platformer", "Celeste"))
        self.assertEqual(status["calls"], 3)  # search + details + stores (the steam id was missing)

    def test_a_game_that_already_has_its_rawg_id_only_needs_the_details(self):
        self.game("celeste", "Celeste", rawg_id=101, steam_id="504230")
        self.rawg.details[101] = rawg_game(101, "Celeste")
        status = self.sync()
        self.assertEqual((status["calls"], status["updated"]), (1, 1))
        self.assertEqual(self.rawg.calls, ["/games/101"])

    def test_a_game_with_everything_filled_is_not_even_looked_at(self):
        self.game("full", "Full", rawg_id=5, slug="full", dev="Dev", genres="RPG", image_url="https://i", steam_id="1",
                  release_date=datetime.date(2020, 1, 1))
        status = self.sync()
        self.assertEqual((status["total"], status["calls"], self.rawg.calls), (0, 0, []))

    def test_an_ambiguous_name_is_left_for_the_admin_with_the_candidates(self):
        self.game("zelda", "Zelda")
        self.rawg.search_results["zelda"] = [rawg_game(1, "Zelda: Link"), rawg_game(2, "Zelda II")]
        status = self.sync()
        self.assertEqual(len(status["ambiguous"]), 1)
        self.assertEqual([c["rawg_id"] for c in status["ambiguous"][0]["candidates"]], [1, 2])
        self.assertIsNone(self.game_row("zelda").rawg_id)

    def test_an_unknown_game_is_reported_as_not_found(self):
        self.game("mystery", "Mystery")
        status = self.sync()
        self.assertEqual(status["not_found"], [{"game_id": "mystery", "name": "Mystery"}])

    def test_a_rawg_id_already_used_by_another_game_is_never_assigned(self):
        self.game("original", "Celeste", rawg_id=101, slug="c", dev="d", genres="g", image_url="https://i", steam_id="1",
                  release_date=datetime.date(2020, 1, 1))
        self.game("copy", "Celeste Copy")
        self.rawg.search_results["celeste copy"] = [rawg_game(101, "Celeste Copy")]
        status = self.sync()
        self.assertEqual(status["duplicates"][0]["other_game_id"], "original")
        self.assertIsNone(self.game_row("copy").rawg_id)

    def test_the_most_played_games_go_first_and_the_budget_ends_the_run(self):
        self.game("rarely", "Rarely")
        self.game("often", "Often")
        self.user("ana")
        for hour in range(3):
            self.session(self.scalar("SELECT id FROM users"), "often", datetime.datetime(2026, 3, 1, 8 + 2 * hour), 30)
        for name, rawg_id in (("rarely", 1), ("often", 2)):
            self.rawg.search_results[name] = [rawg_game(rawg_id, name.capitalize())]
            self.rawg.details[rawg_id] = rawg_game(rawg_id, name.capitalize())
        status = self.sync(max_calls=3)  # search + details + stores for the first game; none left for the second
        self.assertEqual((status["stop_reason"], status["updated"]), ("max_calls", 1))
        self.assertEqual(self.game_row("often").rawg_id, 2)
        self.assertIsNone(self.game_row("rarely").rawg_id)

    def test_cancelling_during_a_run_stops_it_before_the_next_game(self):
        self.game("a", "A")
        self.game("b", "B")
        real_get = self.rawg.__call__

        def cancel_while_searching(url, params=None, timeout=None):
            rawg_sync.cancel()  # what the admin's "cancel" button does, while the first game is being looked up
            return real_get(url, params, timeout)

        with mock.patch.object(rawg_sync.requests, "get", new=cancel_while_searching):
            status = self.sync()
        self.assertEqual((status["state"], status["stop_reason"], status["processed"]), ("cancelled", "cancelled", 1))
        self.assertEqual(len(self.rawg.calls), 1)

    def test_cancel_reports_whether_a_run_was_in_progress(self):
        self.assertFalse(rawg_sync.cancel())
        rawg_sync._status["state"] = "running"
        self.assertTrue(rawg_sync.cancel())
        self.assertTrue(rawg_sync._cancel.is_set())

    def test_a_run_cannot_start_while_another_is_in_progress_nor_without_a_key(self):
        rawg_sync._status["state"] = "running"
        self.assertFalse(rawg_sync.start(10, False))
        rawg_sync._status["state"] = "idle"
        with mock.patch.object(type(rawg_sync.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=""):
            with self.assertRaisesRegex(RuntimeError, "clave"):
                rawg_sync.start(10, False)

    def test_a_refused_key_ends_the_whole_run(self):
        self.game("a", "A")
        self.game("b", "B")
        self.rawg.status_for["/games"] = [401]
        status = self.sync()
        self.assertEqual(status["state"], "finished")
        self.assertTrue(status["stop_reason"].startswith("rawg: RAWG respondió 401"))
        self.assertEqual(self.rawg.calls, ["/games"])  # it did not go on to the next game

    def test_five_errors_in_a_row_stop_the_run_and_fewer_do_not(self):
        for n in range(6):
            self.game(f"g{n}", f"G{n}", rawg_id=n + 1)
        status = self.sync()  # every details call is a 404: ConnectionError for each game
        self.assertEqual((status["stop_reason"], len(status["errors"])), ("errors", 5))
        for n in range(6):
            self.rawg.details[n + 1] = rawg_game(n + 1, f"G{n}")
        self.rawg.details.pop(3)
        again = self.sync()
        self.assertEqual((again["stop_reason"], len(again["errors"]), again["updated"]), ("completed", 1, 5))

    def test_a_failure_in_one_game_does_not_stop_the_others_and_never_shows_the_key(self):
        self.game("a", "A", rawg_id=1)
        self.game("b", "B", rawg_id=2)
        for rawg_id in (1, 2):
            self.rawg.details[rawg_id] = rawg_game(rawg_id, "X")
        real = rawg_sync._apply

        def flaky(game, det, overwrite):
            if game.id == "a":
                raise ValueError(f"cannot apply, key={KEY}")
            return real(game, det, overwrite)

        with mock.patch.object(rawg_sync, "_apply", new=flaky):
            status = self.sync()
        self.assertEqual((status["updated"], status["processed"], len(status["errors"])), (1, 2, 1))
        self.assertNotIn(KEY, str(status["errors"]))

    def test_the_status_of_a_new_run_replaces_the_previous_one(self):
        self.game("a", "A")
        self.sync()
        self.assertEqual(len(rawg_sync.status()["not_found"]), 1)
        self.sync()
        self.assertEqual(len(rawg_sync.status()["not_found"]), 1)  # not two

    def test_a_game_whose_details_change_nothing_is_counted_as_unchanged(self):
        self.game("a", "A", rawg_id=1, slug="a", dev="Maddy Makes Games", genres="Indie,Platformer",
                  image_url="https://img/1.jpg", steam_id="1", release_date=datetime.date(2018, 1, 25))
        self.rawg.details[1] = rawg_game(1, "A", slug="a")
        self.assertEqual(self.sync(overwrite=True)["unchanged"], 1)


class ApplyOneTests(SyncTestCase):
    def test_an_ambiguous_game_is_resolved_by_choosing_its_rawg_entry(self):
        self.game("zelda", "Zelda")
        self.rawg.details[7] = rawg_game(7, "Zelda: Link")
        with database.SessionLocal() as db:
            result = rawg_sync.apply_one(db, "zelda", 7)
        self.assertIn("rawg_id", result["changed"])
        self.assertEqual(result["calls"], 2)  # details + stores
        self.assertEqual(self.game_row("zelda").rawg_id, 7)

    def test_it_refuses_an_unknown_game_and_a_rawg_id_that_belongs_to_another(self):
        self.game("a", "A")
        self.game("b", "B", rawg_id=7)
        with database.SessionLocal() as db:
            with self.assertRaises(LookupError):
                rawg_sync.apply_one(db, "nope", 7)
            with self.assertRaisesRegex(ValueError, "«B»"):
                rawg_sync.apply_one(db, "a", 7)

    def test_without_overwrite_existing_values_are_kept_and_with_it_they_are_replaced(self):
        self.game("a", "A", dev="Mine")
        self.rawg.details[7] = rawg_game(7, "A")
        with database.SessionLocal() as db:
            rawg_sync.apply_one(db, "a", 7)
        self.assertEqual(self.game_row("a").dev, "Mine")
        with database.SessionLocal() as db:
            rawg_sync.apply_one(db, "a", 7, overwrite=True)
        self.assertEqual(self.game_row("a").dev, "Maddy Makes Games")

    def test_a_rawg_failure_propagates_for_the_route_to_report(self):
        self.game("a", "A")
        with database.SessionLocal() as db:
            with self.assertRaises(ConnectionError):
                rawg_sync.apply_one(db, "a", 404)
        self.rawg.status_for["/games/9"] = [429]
        with database.SessionLocal() as db:
            with self.assertRaises(rawg_sync.RawgFatal):
                rawg_sync.apply_one(db, "a", 9)
