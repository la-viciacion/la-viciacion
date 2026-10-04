import datetime
import json
import unittest

from src.crud import data_export
from src.database import models, schemas
from src.utils import messages as msg
from src.utils import seasons
from tests.sqlite_db import make_session

YEAR = seasons.current()
D = datetime.datetime


def at(day: int, hour: int, minute: int = 0) -> datetime.datetime:
    """A moment of the running season, in the past."""
    return D(YEAR, 1, day, hour, minute)


def parse(**sections) -> schemas.ExportFile:
    return schemas.ExportFile.model_validate({"format": data_export.FORMAT, "version": data_export.VERSION, **sections})


def session(game="doom", start=None, hours=1, platform="pc"):
    start = start or at(2, 10)
    return {"game_id": game, "platform": platform, "start_time": start.isoformat(), "end_time": (start + datetime.timedelta(hours=hours)).isoformat()}


class DataTestCase(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.ana = models.User(id=1, username="ana", name="Ana", email="a@x.es", is_admin=0, is_active=1)
        self.root = models.User(id=2, username="root", name="Root", email="r@x.es", is_admin=1, is_active=1)
        self.db.add_all([
            self.ana, self.root,
            models.Game(id="doom", name="Doom"), models.Game(id="hades", name="Hades"),
            models.PlatformTag(id="pc", name="PC"),
        ])
        self.db.commit()

    def run_import(self, data, actor=None, user=None, dry_run=False):
        return data_export.import_data(self.db, actor or self.ana, user or self.ana, data, dry_run)

    def count(self, model, **filters):
        return self.db.query(model).filter_by(**filters).count()


class ExportTests(DataTestCase):
    def setUp(self):
        super().setUp()
        self.db.add_all([
            models.GameTimer(user_id=1, game_id="doom", platform="pc", start_time=at(2, 10), end_time=at(2, 11), duration_seconds=3600, is_active=False, notes="n"),
            models.GameTimer(user_id=1, game_id="doom", platform="pc", start_time=at(3, 10), is_active=True),  # running: not exported
            models.GameTimer(user_id=2, game_id="hades", platform="pc", start_time=at(2, 10), end_time=at(2, 11), duration_seconds=3600, is_active=False),
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=at(2, 10).date(), completed=1, completed_date=at(5, 1).date()),
            models.GameScore(user_id=1, game_id="doom", score=90),
            models.UserWishlist(user_id=1, game_id="hades"),
            models.Achievement(id=1, key="first", title="First"),
        ])
        self.db.commit()
        self.db.add(models.UserAchievement(user_id=1, achievement_id=1, date=at(2, 1).date(), game_id="doom"))
        self.db.commit()

    def export(self):
        return data_export.export_user(self.db, self.ana, D(YEAR, 6, 1, 12, 30, 15, 999))

    def test_it_holds_only_what_is_the_players_and_names_the_format(self):
        out = self.export()
        self.assertEqual((out["format"], out["version"], out["exported_at"]), ("laviciacion-export", 1, f"{YEAR}-06-01T12:30:15"))
        self.assertEqual(out["user"], {"username": "ana", "name": "Ana"})
        self.assertEqual([s["game_id"] for s in out["sessions"]], ["doom"])  # finished ones only, and only ana's
        self.assertEqual(out["sessions"][0]["notes"], "n")
        self.assertEqual(out["scores"], [{"game_id": "doom", "score": 90}])
        self.assertEqual([w["game_id"] for w in out["wishlist"]], ["hades"])
        self.assertEqual(out["achievements"], [{"key": "first", "date": f"{YEAR}-01-02", "game_id": "doom"}])

    def test_it_carries_the_games_and_platforms_it_mentions_and_nothing_personal(self):
        out = self.export()
        self.assertEqual({g["id"] for g in out["games"]}, {"doom", "hades"})
        self.assertEqual(out["platforms"], [{"id": "pc", "name": "PC"}])
        self.assertNotIn("a@x.es", json.dumps(out))

    def test_nothing_derived_is_in_it(self):
        out = self.export()
        self.assertNotIn("season", out["sessions"][0])
        self.assertNotIn("played_time", out["library"][0])

    def test_what_it_exports_is_what_the_import_accepts(self):
        out = json.loads(json.dumps(self.export()))
        self.assertTrue(data_export.is_supported(schemas.ExportFile.model_validate(out)))

    def test_only_a_file_of_this_format_and_version_is_supported(self):
        self.assertFalse(data_export.is_supported(schemas.ExportFile(format="other", version=1)))
        self.assertFalse(data_export.is_supported(schemas.ExportFile(format=data_export.FORMAT, version=2)))


class ImportSessionsTests(DataTestCase):
    def test_sessions_are_added_with_their_library_entry_and_a_recomputed_duration(self):
        body = session(start=at(2, 10), hours=2)
        body["duration_seconds"] = 5  # a lie: the file's value is never trusted
        report = self.run_import(parse(sessions=[body]))
        self.assertEqual(report["sessions"], {"imported": 1, "existing": 0, "skipped": 0})
        saved = self.db.query(models.GameTimer).one()
        self.assertEqual((saved.duration_seconds, saved.is_active, saved.user_id), (7200, False, 1))
        self.assertEqual(self.count(models.UserGame, user_id=1, game_id="doom", platform="pc", season=YEAR), 1)

    def test_importing_the_same_file_twice_changes_nothing(self):
        data = parse(sessions=[session()], library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR}-01-02"}], scores=[{"game_id": "doom", "score": 70}])
        self.run_import(data)
        again = self.run_import(data)
        self.assertEqual((again["sessions"]["imported"], again["sessions"]["existing"]), (0, 1))
        self.assertEqual((again["library"]["imported"], again["library"]["existing"]), (0, 1))
        self.assertEqual((again["scores"]["imported"], again["scores"]["existing"]), (0, 1))
        self.assertEqual(self.count(models.GameTimer), 1)
        self.assertEqual(self.count(models.UserGame), 1)

    def test_what_the_account_has_is_never_overwritten(self):
        self.db.add(models.GameScore(user_id=1, game_id="doom", score=10))
        self.db.add(models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=at(2, 1).date(), completed=0))
        self.db.commit()
        self.run_import(parse(scores=[{"game_id": "doom", "score": 99}], library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR}-01-09", "completed": True, "completed_date": f"{YEAR}-01-10"}]))
        self.assertEqual(self.db.query(models.GameScore).one().score, 10)
        entry = self.db.query(models.UserGame).one()
        self.assertEqual((entry.completed, entry.started_date), (0, at(2, 1).date()))

    def test_a_session_that_overlaps_another_is_skipped_and_touching_ones_are_not(self):
        self.db.add(models.GameTimer(user_id=1, game_id="hades", platform="pc", start_time=at(2, 10), end_time=at(2, 12), duration_seconds=7200, is_active=False))
        self.db.commit()
        report = self.run_import(parse(sessions=[
            session(start=at(2, 11)),  # inside the existing one
            session(start=at(2, 12)),  # starts when it ends: fine
            session(game="hades", start=at(2, 12, 30)),  # overlaps the one just imported (12:00-13:00)
            session(start=at(2, 9)),  # ends when the existing one starts: fine
        ]))
        self.assertEqual(report["sessions"], {"imported": 2, "existing": 0, "skipped": 2})
        self.assertEqual({p["reason"] for p in report["problems"]}, {msg.IMPORT_OVERLAP})

    def test_two_sessions_of_the_file_that_overlap_keep_the_first(self):
        report = self.run_import(parse(sessions=[session(start=at(2, 10)), session(game="hades", start=at(2, 10, 30))]))
        self.assertEqual(report["sessions"], {"imported": 1, "existing": 0, "skipped": 1})
        self.assertEqual(self.db.query(models.GameTimer).one().game_id, "doom")

    def test_a_running_timer_blocks_what_starts_before_it_is_over(self):
        self.db.add(models.GameTimer(user_id=1, game_id="doom", platform="pc", start_time=at(2, 11), is_active=True))
        self.db.commit()
        report = self.run_import(parse(sessions=[session(start=at(2, 10, 30))]))
        self.assertEqual(report["sessions"]["skipped"], 1)

    def test_impossible_times_are_skipped(self):
        future = datetime.datetime.now() + datetime.timedelta(days=1)
        backwards = {**session(), "end_time": at(2, 9).isoformat()}
        report = self.run_import(parse(sessions=[backwards, session(start=future)]))
        self.assertEqual(report["sessions"]["skipped"], 2)
        self.assertEqual({p["reason"] for p in report["problems"]}, {msg.IMPORT_BAD_TIMES, msg.IMPORT_IN_THE_FUTURE})

    def test_a_time_with_a_zone_is_not_a_valid_file(self):
        with self.assertRaises(ValueError):
            parse(sessions=[{**session(), "start_time": f"{YEAR}-01-02T10:00:00+02:00"}])

    def test_the_new_sessions_are_not_a_running_timer(self):
        self.run_import(parse(sessions=[session()]))
        self.assertEqual(self.count(models.GameTimer, is_active=True), 0)


class ImportCatalogueTests(DataTestCase):
    def test_a_game_the_database_lacks_is_skipped_for_a_player_and_named(self):
        report = self.run_import(parse(
            games=[{"id": "zelda", "name": "Zelda"}], sessions=[session(game="zelda")], scores=[{"game_id": "zelda", "score": 50}],
        ))
        self.assertEqual(report["sessions"]["skipped"], 1)
        self.assertEqual(report["scores"]["skipped"], 1)
        self.assertEqual(report["problems"][0], {"kind": "sessions", "label": f"Zelda · {YEAR}-01-02 10:00", "reason": msg.IMPORT_UNKNOWN_GAME})
        self.assertEqual(self.count(models.Game, id="zelda"), 0)

    def test_a_game_is_found_by_name_when_its_id_differs(self):
        report = self.run_import(parse(games=[{"id": "doom-1993", "name": "doom"}], sessions=[session(game="doom-1993")]))
        self.assertEqual(report["sessions"]["imported"], 1)
        self.assertEqual(self.db.query(models.GameTimer).one().game_id, "doom")

    def test_a_platform_the_catalogue_lacks_is_skipped_for_a_player(self):
        report = self.run_import(parse(sessions=[session(platform="switch")]))
        self.assertEqual((report["sessions"]["skipped"], report["problems"][0]["reason"]), (1, msg.IMPORT_UNKNOWN_PLATFORM))

    def test_a_platform_is_found_by_name_too(self):
        report = self.run_import(parse(platforms=[{"id": "ordenador", "name": "pc"}], sessions=[session(platform="ordenador")]))
        self.assertEqual(report["sessions"]["imported"], 1)
        self.assertEqual(self.db.query(models.GameTimer).one().platform, "pc")

    def test_an_admin_creates_the_missing_games_and_platforms(self):
        report = self.run_import(
            parse(games=[{"id": "zelda", "name": "Zelda", "genres": "Adventure"}], platforms=[{"id": "switch", "name": "Switch"}], sessions=[session(game="zelda", platform="switch")]),
            actor=self.root,
        )
        self.assertEqual((report["sessions"]["imported"], report["created"]), (1, {"games": 1, "platforms": 1}))
        self.assertEqual(self.db.get(models.Game, "zelda").genres, "Adventure")
        self.assertEqual(self.db.get(models.PlatformTag, "switch").name, "Switch")

    def test_an_admin_does_not_create_a_game_whose_name_is_taken_but_uses_that_one(self):
        report = self.run_import(parse(games=[{"id": "other", "name": "Hades"}], sessions=[session(game="other")]), actor=self.root)
        self.assertEqual((report["created"]["games"], self.db.query(models.GameTimer).one().game_id), (0, "hades"))


class ImportSeasonsTests(DataTestCase):
    def old(self):
        return D(YEAR - 1, 5, 1, 10)

    def test_a_player_cannot_import_a_closed_season(self):
        report = self.run_import(parse(sessions=[session(start=self.old())], library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR - 1}-05-01"}]))
        self.assertEqual((report["sessions"]["skipped"], report["library"]["skipped"]), (1, 1))
        self.assertEqual({p["reason"] for p in report["problems"]}, {msg.IMPORT_CLOSED_SEASON})
        self.assertEqual(self.count(models.GameTimer), 0)

    def test_an_admin_can(self):
        report = self.run_import(parse(sessions=[session(start=self.old())]), actor=self.root)
        self.assertEqual(report["sessions"]["imported"], 1)
        self.assertEqual(self.count(models.UserGame, season=YEAR - 1), 1)


class ImportLibraryTests(DataTestCase):
    def test_a_completion_is_kept_with_its_date(self):
        self.run_import(parse(library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR}-01-02", "completed": True, "completed_date": f"{YEAR}-01-20", "completion_time": 3600}]))
        entry = self.db.query(models.UserGame).one()
        self.assertEqual((entry.completed, entry.completed_date, entry.completion_time), (1, datetime.date(YEAR, 1, 20), 3600))

    def test_a_game_is_completed_once_per_season(self):
        self.db.add(models.UserGame(user_id=1, game_id="doom", platform="ps5", started_date=at(2, 1).date(), completed=1, completed_date=at(4, 1).date()))
        self.db.add(models.PlatformTag(id="ps5", name="PS5"))
        self.db.commit()
        self.run_import(parse(library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR}-01-03", "completed": True, "completed_date": f"{YEAR}-01-20"}]))
        self.assertEqual(self.count(models.UserGame, user_id=1, game_id="doom", completed=1), 1)
        self.assertEqual(self.count(models.UserGame, user_id=1, game_id="doom"), 2)

    def test_a_completion_date_outside_the_season_falls_back_to_the_start(self):
        self.run_import(parse(library=[{"game_id": "doom", "platform": "pc", "started_date": f"{YEAR}-01-02", "completed": True, "completed_date": f"{YEAR + 1}-01-01"}]))
        self.assertEqual(self.db.query(models.UserGame).one().completed_date, datetime.date(YEAR, 1, 2))


class ImportScoresAndWishesTests(DataTestCase):
    def test_a_rating_needs_the_game_in_the_library_and_a_wish_needs_it_not_to_be(self):
        self.db.add(models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=at(2, 1).date(), completed=0))
        self.db.commit()
        report = self.run_import(parse(
            scores=[{"game_id": "doom", "score": 80}, {"game_id": "hades", "score": 60}],
            wishlist=[{"game_id": "doom"}, {"game_id": "hades"}],
        ))
        self.assertEqual(report["scores"], {"imported": 1, "existing": 0, "skipped": 1})
        self.assertEqual(report["wishlist"], {"imported": 1, "existing": 0, "skipped": 1})
        self.assertEqual({p["reason"] for p in report["problems"]}, {msg.IMPORT_NOT_IN_LIBRARY, msg.IMPORT_ALREADY_PLAYED})

    def test_a_rating_follows_the_sessions_that_open_the_library_entry(self):
        report = self.run_import(parse(sessions=[session()], scores=[{"game_id": "doom", "score": 80}]))
        self.assertEqual(report["scores"]["imported"], 1)

    def test_a_rating_out_of_range_is_not_a_valid_file(self):
        with self.assertRaises(ValueError):
            parse(scores=[{"game_id": "doom", "score": 101}])


class DryRunTests(DataTestCase):
    def test_it_says_what_would_happen_and_writes_nothing(self):
        data = parse(
            games=[{"id": "zelda", "name": "Zelda"}], platforms=[{"id": "switch", "name": "Switch"}],
            sessions=[session(), session(game="zelda", start=at(3, 10), platform="switch")], scores=[{"game_id": "doom", "score": 80}],
        )
        report = self.run_import(data, actor=self.root, user=self.ana, dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertEqual((report["sessions"]["imported"], report["scores"]["imported"], report["created"]), (2, 1, {"games": 1, "platforms": 1}))
        for model in (models.GameTimer, models.UserGame, models.GameScore):
            self.assertEqual(self.count(model), 0, model)
        self.assertIsNone(self.db.get(models.Game, "zelda"))
        self.assertIsNone(self.db.get(models.PlatformTag, "switch"))

    def test_the_real_run_gives_the_same_report(self):
        data = parse(sessions=[session()], scores=[{"game_id": "doom", "score": 80}])
        preview = self.run_import(data, dry_run=True)
        done = self.run_import(data)
        self.assertEqual({**preview, "dry_run": False}, done)


class ReportTests(DataTestCase):
    def test_only_the_first_problems_are_listed_but_all_are_counted(self):
        many = [session(game="nope", start=at(2, 0) + datetime.timedelta(minutes=2 * i), hours=0.01) for i in range(40)]
        report = self.run_import(parse(sessions=many))
        self.assertEqual((report["problems_total"], len(report["problems"])), (40, data_export.PROBLEMS_SHOWN))

    def test_it_is_plain_data(self):
        json.dumps(self.run_import(parse(sessions=[session()])))

    def test_another_player_cannot_see_into_the_account_it_imports_to(self):
        self.run_import(parse(sessions=[session()]), actor=self.root, user=self.ana)
        self.assertEqual(self.count(models.GameTimer, user_id=1), 1)
        self.assertEqual(self.count(models.GameTimer, user_id=2), 0)


if __name__ == "__main__":
    unittest.main()
