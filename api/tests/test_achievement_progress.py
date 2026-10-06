import datetime
import unittest

from src.crud import achievement_progress as progress
from src.crud import group
from src.database import models
from src.utils import seasons
from tests.sqlite_db import make_session

YEAR = seasons.current()
TODAY = datetime.date(YEAR, 6, 10)


def day(month, d, hour=10):
    return datetime.datetime(YEAR, month, d, hour)


class TargetTests(unittest.TestCase):
    def test_the_cumulative_families_have_a_bar(self):
        self.assertEqual(progress.target_of("PLAYED_200_HOURS"), ("hours", "horas", 200))
        self.assertEqual(progress.target_of("PLAYED_30_DAYS"), ("days", "días jugados", 30))
        self.assertEqual(progress.target_of("PLAYED_42_GAMES"), ("games", "juegos jugados", 42))
        self.assertEqual(progress.target_of("COMPLETED_5_GAMES"), ("completed", "juegos completados", 5))
        self.assertEqual(progress.target_of("PLAYED_500_HOURS_GAME"), ("game_hours", "horas en un mismo juego", 500))
        self.assertEqual(progress.target_of("STREAK_15_DAYS"), ("streak", "días seguidos", 15))
        self.assertEqual(progress.target_of("PLAYED_5000_HOURS_LIFETIME"), ("hours", "horas", 5000))

    def test_the_ones_about_a_moment_have_none(self):
        for key in ("PLAYED_8_HOURS_DAY", "PLAYED_4_HOURS_SESSION", "PLAYED_5_GAMES_DAY", "EARLY_RISER", "RELEASE_DAY", "TEAMWORK"):
            self.assertIsNone(progress.target_of(key), key)

    def test_every_threshold_the_checks_use_has_one(self):
        from src.crud import achievements as checks

        for table in (checks.TOTAL_HOURS, checks.TOTAL_DAYS, checks.PLAYED_GAMES, checks.COMPLETED_GAMES, checks.HOURS_IN_A_GAME,
                      checks.STREAKS, checks.LIFETIME_TOTAL_HOURS, checks.LIFETIME_TOTAL_DAYS, checks.LIFETIME_PLAYED_GAMES,
                      checks.LIFETIME_COMPLETED_GAMES, checks.LIFETIME_HOURS_IN_A_GAME):
            for ach, needed in table:
                self.assertEqual(progress.target_of(ach.name)[2], needed, ach.name)

    def test_the_bar_never_goes_past_its_goal(self):
        self.assertEqual(progress.bar(250, 200, "horas"), {"current": 200, "target": 200, "unit": "horas"})
        self.assertEqual(progress.bar(12.345, 100, "horas"), {"current": 12.3, "target": 100, "unit": "horas"})
        self.assertEqual(progress.bar(3, 7, "días"), {"current": 3, "target": 7, "unit": "días"})


class CatalogProgressTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        keys = [
            ("PLAYED_10_HOURS_X", 0),  # not a family: no bar
            ("PLAYED_100_HOURS", 0), ("PLAYED_7_DAYS", 0), ("PLAYED_10_GAMES", 0), ("STREAK_7_DAYS", 0), ("PLAYED_100_HOURS_GAME", 0),
            ("PLAYED_8_HOURS_DAY", 0), ("PLAYED_500_HOURS_LIFETIME", 0), ("PLAYED_10_GAMES_DAY", 1),
        ]
        self.db.add_all([models.User(id=1, username="ana", name="Ana", is_active=1, is_admin=0)])
        for i, (key, secret) in enumerate(keys, start=1):
            self.db.add(models.Achievement(id=i, key=key, title=key, message="x", active=True, secret=bool(secret), special=0, valid_from_season=2023))
        self.db.add_all([models.Game(id="doom", name="Doom"), models.Game(id="hades", name="Hades")])
        # three consecutive days (ending yesterday), 2 h each: 6 h, 3 days, 2 games, best game 4 h
        for n, (game, hours) in enumerate([("doom", 2), ("doom", 2), ("hades", 2)]):
            start = datetime.datetime(YEAR, 6, 7 + n, 10)
            self.db.add(models.GameTimer(
                user_id=1, game_id=game, start_time=start, end_time=start + datetime.timedelta(hours=hours),
                duration_seconds=hours * 3600, is_active=False,
            ))
        self.db.add(models.UserGame(user_id=1, game_id="doom", started_date=datetime.date(YEAR, 6, 7), completed=0))
        self.db.add(models.UserGame(user_id=1, game_id="hades", started_date=datetime.date(YEAR, 6, 9), completed=0))
        self.db.commit()

    def catalog(self):
        return {a["key"]: a for a in group.achievements_catalog(self.db, 1, TODAY) if not a["hidden"]}

    def test_each_cumulative_achievement_shows_how_far_the_player_is(self):
        got = self.catalog()
        self.assertEqual(got["PLAYED_100_HOURS"]["progress"], {"current": 6, "target": 100, "unit": "horas"})
        self.assertEqual(got["PLAYED_7_DAYS"]["progress"], {"current": 3, "target": 7, "unit": "días jugados"})
        self.assertEqual(got["PLAYED_10_GAMES"]["progress"], {"current": 2, "target": 10, "unit": "juegos jugados"})
        self.assertEqual(got["PLAYED_100_HOURS_GAME"]["progress"], {"current": 4, "target": 100, "unit": "horas en un mismo juego"})
        self.assertEqual(got["STREAK_7_DAYS"]["progress"], {"current": 3, "target": 7, "unit": "días seguidos"})

    def test_a_lifetime_one_counts_the_whole_history(self):
        last = datetime.datetime(YEAR - 1, 3, 1, 10)
        self.db.add(models.GameTimer(user_id=1, game_id="doom", start_time=last, end_time=last + datetime.timedelta(hours=10), duration_seconds=36000, is_active=False))
        self.db.commit()
        got = self.catalog()
        self.assertEqual(got["PLAYED_500_HOURS_LIFETIME"]["progress"]["current"], 16)
        self.assertEqual(got["PLAYED_100_HOURS"]["progress"]["current"], 6)  # the season one ignores last year

    def test_the_streak_is_the_current_run(self):
        self.assertEqual(group.achievements_catalog(self.db, 1, datetime.date(YEAR, 6, 15))[4]["progress"]["current"], 0)

    def test_the_ones_about_a_moment_and_the_unknown_have_no_bar(self):
        got = self.catalog()
        self.assertIsNone(got["PLAYED_8_HOURS_DAY"]["progress"])
        self.assertIsNone(got["PLAYED_10_HOURS_X"]["progress"])

    def test_a_secret_one_the_player_has_not_earned_comes_hidden_without_a_bar(self):
        hidden = [a for a in group.achievements_catalog(self.db, 1, TODAY) if a["hidden"]]
        self.assertEqual(len(hidden), 1)
        self.assertNotIn("progress", hidden[0])

    def test_once_earned_there_is_no_bar(self):
        self.db.add(models.UserAchievement(user_id=1, achievement_id=2, date=datetime.date(YEAR, 6, 9)))
        self.db.commit()
        got = self.catalog()
        self.assertIsNone(got["PLAYED_100_HOURS"]["progress"])
        self.assertTrue(got["PLAYED_100_HOURS"]["unlocked_by_me"])

    def test_one_earned_in_a_past_season_still_shows_this_season_and_is_known(self):
        self.db.add(models.UserAchievement(user_id=1, achievement_id=2, date=datetime.date(YEAR - 1, 6, 9)))
        self.db.commit()
        got = self.catalog()
        self.assertFalse(got["PLAYED_100_HOURS"]["unlocked_by_me"])  # not this season
        self.assertEqual(got["PLAYED_100_HOURS"]["progress"]["current"], 6)
        self.assertIsNotNone(got["PLAYED_100_HOURS"]["description"])  # but whoever earned it once knows what it is

    def test_a_lifetime_one_earned_in_a_past_season_has_no_bar(self):
        self.db.add(models.UserAchievement(user_id=1, achievement_id=8, date=datetime.date(YEAR - 1, 6, 9)))
        self.db.commit()
        self.assertIsNone(self.catalog()["PLAYED_500_HOURS_LIFETIME"]["progress"])


class SeasonViewTests(unittest.TestCase):
    """The season achievements of a chosen season: what is said of them is about that season only."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, username="ana", name="Ana", is_active=1, is_admin=0),
            models.User(id=2, username="bea", name="Bea", is_active=1, is_admin=0),
            models.Achievement(id=1, key="PLAYED_100_HOURS", title="100 h", message="*{}* 100 horas", active=True, secret=False, special=0, valid_from_season=2023),
            models.Achievement(id=2, key="PLAYED_7_DAYS", title="7 días", message="x", active=True, secret=False, special=0, valid_from_season=YEAR),
            models.Achievement(id=3, key="PLAYED_500_HOURS_LIFETIME", title="500 h", message="x", active=True, secret=False, special=0, valid_from_season=2023),
            models.Achievement(id=4, key="EARLY_RISER", title="Madrugador", message="x", active=True, secret=True, special=0, valid_from_season=2023),
        ])
        past = datetime.date(YEAR - 1, 5, 1)
        self.db.add_all([
            models.UserAchievement(user_id=1, achievement_id=1, date=past),
            models.UserAchievement(user_id=2, achievement_id=1, date=past),
            models.UserAchievement(user_id=2, achievement_id=1, date=datetime.date(YEAR, 2, 1)),
            models.UserAchievement(user_id=1, achievement_id=3, date=past),
            models.UserAchievement(user_id=1, achievement_id=4, date=past),
        ])
        self.db.commit()

    def view(self, season=None, viewer=1):
        return {a.get("key", a["id"]): a for a in group.achievements_catalog(self.db, viewer, TODAY, season)}

    def test_a_past_season_says_who_had_it_then_and_whether_the_viewer_did(self):
        got = self.view(YEAR - 1)
        self.assertTrue(got["PLAYED_100_HOURS"]["unlocked_by_me"])
        self.assertEqual(got["PLAYED_100_HOURS"]["unlocked_by"], 2)
        self.assertEqual([p["times"] for p in got["PLAYED_100_HOURS"]["players"]], [1, 1])  # once a season

    def test_the_running_season_counts_only_this_season(self):
        got = self.view()
        self.assertFalse(got["PLAYED_100_HOURS"]["unlocked_by_me"])
        self.assertEqual(got["PLAYED_100_HOURS"]["unlocked_by"], 1)
        self.assertEqual(got["PLAYED_100_HOURS"]["players"][0]["name"], "Bea")
        self.assertEqual(self.view(YEAR)["PLAYED_100_HOURS"]["unlocked_by"], 1)

    def test_an_achievement_that_did_not_exist_yet_is_not_listed(self):
        self.assertNotIn("PLAYED_7_DAYS", self.view(YEAR - 1))
        self.assertIn("PLAYED_7_DAYS", self.view(YEAR))

    def test_a_closed_season_has_no_bars(self):
        past = self.view(YEAR - 1)
        self.assertTrue(all(a["progress"] is None for a in past.values() if not a.get("hidden")))
        self.assertIsNotNone(self.view(YEAR)["PLAYED_100_HOURS"]["progress"])

    def test_the_lifetime_ones_do_not_depend_on_the_season(self):
        for season in (YEAR - 1, YEAR):
            got = self.view(season)["PLAYED_500_HOURS_LIFETIME"]
            self.assertTrue(got["unlocked_by_me"])
            self.assertTrue(got["lifetime"])

    def test_a_secret_one_stays_known_to_whoever_earned_it_in_any_season(self):
        got = self.view(YEAR)["EARLY_RISER"]
        self.assertFalse(got["hidden"])
        self.assertFalse(got["unlocked_by_me"])  # not this season
        self.assertTrue(self.view(YEAR - 1)["EARLY_RISER"]["unlocked_by_me"])
        self.assertTrue(self.view(YEAR, viewer=2)[4]["hidden"])  # bea never had it

    def test_a_future_season_is_refused_by_the_route(self):
        from fastapi import HTTPException
        from src.routers import group as route

        with self.assertRaises(HTTPException) as ctx:
            route.get_achievements(YEAR + 1, models.User(id=1), self.db)
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
