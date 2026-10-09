"""The bulk sync of the average times against HowLongToBeat (MariaDB required, see api_support.py). HowLongToBeat is a
fake, the throttling sleeps are skipped and the background thread runs in the test, so a whole sync is one call to
`start()` followed by a look at `status()`."""
from types import SimpleNamespace
from unittest import mock

from src.database import database, models
from src.utils import hltb_sync
from tests.api_support import ApiTestCase


def entry(name, seconds=36000, game_id=1, year=None, kind="game"):
    return SimpleNamespace(
        game_id=game_id, game_name=name, game_alias=None, game_type=kind, release_world=year, json_content={"comp_main": seconds}
    )


class FakeHowLongToBeat:
    """Answers each search from a dict keyed by the lower-cased name; None is a failed request."""

    answers: dict = {}
    searched: list = []

    def __init__(self, minimum_similarity=0.4):
        pass

    def search(self, name, similarity_case_sensitive=True):
        self.searched.append(name)
        return self.answers.get(name.lower(), [])


class SameThread:
    """Runs the sync inside `start()`, so the test sees the finished status."""

    def __init__(self, target, daemon):
        self.target = target

    def start(self):
        self.target()


class HltbSyncTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        FakeHowLongToBeat.answers, FakeHowLongToBeat.searched = {}, []
        hltb_sync._status.clear()
        hltb_sync._status["state"] = "idle"
        hltb_sync._cancel.clear()
        for patcher in (
            mock.patch.object(hltb_sync, "HowLongToBeat", new=FakeHowLongToBeat),
            mock.patch.object(hltb_sync.time, "sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def sync(self):
        self.assertTrue(hltb_sync.start())
        return hltb_sync.status()

    def avg_time(self, game_id):
        with database.SessionLocal() as db:
            return db.get(models.Game, game_id).avg_time


class SyncRunTests(HltbSyncTestCase):
    def setUp(self):
        super().setUp()
        # `threading` is the global module: only these tests, which make no request, can swap its Thread
        patcher = mock.patch.object(hltb_sync.threading, "Thread", new=SameThread)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_clear_match_replaces_the_stored_time_even_one_edited_by_hand(self):
        self.game("hades", "Hades", avg_time=111)
        FakeHowLongToBeat.answers = {"hades": [entry("Hades", seconds=72000), entry("Hades II", seconds=1)]}
        status = self.sync()
        self.assertEqual((status["state"], status["stop_reason"], status["updated"]), ("finished", "completed", 1))
        self.assertEqual(self.avg_time("hades"), 72000)

    def test_a_time_that_is_already_right_is_not_counted_as_an_update(self):
        self.game("hades", "Hades", avg_time=72000)
        FakeHowLongToBeat.answers = {"hades": [entry("Hades", seconds=72000)]}
        status = self.sync()
        self.assertEqual((status["updated"], status["unchanged"]), (0, 1))

    def test_doubtful_missing_and_timeless_games_are_reported_and_left_alone(self):
        for game_id, name in (("re", "Resident Evil"), ("zelda", "Zelda"), ("coop", "Overcooked")):
            self.game(game_id, name, avg_time=5)
        FakeHowLongToBeat.answers = {
            "resident evil": [entry("Resident Evil 4", 100 * 3600), entry("Resident Evil 5", 200 * 3600)],
            "overcooked": [entry("Overcooked", seconds=0)],
        }
        status = self.sync()
        self.assertEqual([a["name"] for a in status["ambiguous"]], ["Resident Evil"])
        self.assertEqual(
            sorted((c["name"], c["hours"]) for c in status["ambiguous"][0]["candidates"]),
            [("Resident Evil 4", 100.0), ("Resident Evil 5", 200.0)],
        )
        self.assertEqual([n["name"] for n in status["not_found"]], ["Zelda"])
        self.assertEqual([n["name"] for n in status["no_time"]], ["Overcooked"])
        self.assertEqual({self.avg_time(g) for g in ("re", "zelda", "coop")}, {5})

    def test_the_name_is_searched_without_colons_and_the_year_tells_remakes_apart(self):
        import datetime

        self.game("prey17", "Prey: 2017", release_date=datetime.date(2017, 5, 5), avg_time=0)
        self.game("prey06", "Prey", release_date=datetime.date(2006, 7, 11), avg_time=0)
        FakeHowLongToBeat.answers = {
            "prey 2017": [entry("Prey 2017", 3600)],
            "prey": [entry("Prey", 7200, game_id=1, year=2006), entry("Prey", 36000, game_id=2, year=2017)],
        }
        self.sync()
        self.assertIn("Prey 2017", FakeHowLongToBeat.searched)
        self.assertEqual((self.avg_time("prey17"), self.avg_time("prey06")), (3600, 7200))

    def test_the_most_played_games_go_first(self):
        import datetime

        ana = self.user("ana")
        self.game("a-first", "Alpha")
        self.game("z-played", "Zulu")
        self.session(ana, "z-played", datetime.datetime(2026, 1, 1, 10), 30)
        self.sync()
        self.assertEqual(FakeHowLongToBeat.searched, ["Zulu", "Alpha"])

    def test_five_failed_requests_in_a_row_stop_the_run(self):
        for n in range(7):
            self.game(f"g{n}", f"Game {n}")
        FakeHowLongToBeat.answers = {f"game {n}": None for n in range(7)}
        status = self.sync()
        self.assertEqual((status["stop_reason"], len(status["errors"])), ("errors", 5))

    def test_one_failure_among_good_games_does_not_stop_the_run(self):
        self.game("bad", "Bad")
        self.game("good", "Good", avg_time=0)
        FakeHowLongToBeat.answers = {"bad": None, "good": [entry("Good", 3600)]}
        status = self.sync()
        self.assertEqual((status["stop_reason"], len(status["errors"]), status["updated"]), ("completed", 1, 1))

    def test_only_one_run_at_a_time_and_a_cancel_stops_it(self):
        hltb_sync._status["state"] = "running"
        self.assertFalse(hltb_sync.start())
        self.assertTrue(hltb_sync.cancel())
        hltb_sync._status["state"] = "finished"
        self.assertFalse(hltb_sync.cancel())


class SyncRoutesTests(HltbSyncTestCase):
    def setUp(self):
        super().setUp()
        self.root = self.user("root", admin=True)
        self.ana = self.user("ana")

    def admin(self, method, path, **kwargs):
        return self.api(method, f"/manage{path}", as_user="root", **kwargs)

    def test_only_admins_reach_it(self):
        self.assertEqual(self.api("GET", "/manage/hltb-sync/status", as_user="ana").status_code, 403)
        self.assertEqual(self.api("POST", "/manage/hltb-sync/start", as_user="ana", json={"confirm": "SINCRONIZAR"}).status_code, 403)

    def test_the_estimate_counts_the_games_without_calling_hltb(self):
        self.game("hades", "Hades")
        body = self.admin("GET", "/hltb-sync/estimate").json()
        self.assertEqual(body["total_games"], 1)
        self.assertEqual(FakeHowLongToBeat.searched, [])

    def test_starting_needs_the_phrase_and_refuses_a_second_run(self):
        self.assertEqual(self.admin("POST", "/hltb-sync/start", json={"confirm": "yes"}).status_code, 400)
        with mock.patch.object(hltb_sync, "start", return_value=False):
            self.assertEqual(self.admin("POST", "/hltb-sync/start", json={"confirm": "SINCRONIZAR"}).status_code, 409)

    def test_a_started_run_returns_its_status_and_can_be_cancelled(self):
        with mock.patch.object(hltb_sync, "start", return_value=True), mock.patch.object(hltb_sync, "status", return_value={"state": "running"}):
            response = self.admin("POST", "/hltb-sync/start", json={"confirm": "SINCRONIZAR"})
        self.assertEqual((response.status_code, response.json()), (202, {"state": "running"}))
        with mock.patch.object(hltb_sync, "cancel", return_value=True):
            self.assertEqual(self.admin("POST", "/hltb-sync/cancel").json(), {"cancelling": True})
