"""The recap of a month or a season (crud/recap): the periods, the pure figures and the whole thing over a database."""
import datetime
import unittest

from src.crud import recap
from src.database import models
from tests.sqlite_db import make_session

HOUR = 3600
D = datetime.datetime


def played(user, game, start, hours=1.0):
    seconds = int(hours * HOUR)
    return recap.Played(user, game, start, start + datetime.timedelta(seconds=seconds), seconds)


class PeriodTests(unittest.TestCase):
    def test_a_month_and_a_season_are_told_apart_by_the_format(self):
        month, year = recap.parse_period("2026-09"), recap.parse_period("2026")
        self.assertEqual((month.kind, month.start, month.end), ("month", datetime.date(2026, 9, 1), datetime.date(2026, 10, 1)))
        self.assertEqual((year.kind, year.start, year.end), ("year", datetime.date(2026, 1, 1), datetime.date(2027, 1, 1)))
        self.assertEqual((month.key, year.key), ("2026-09", "2026"))

    def test_december_ends_on_the_first_of_january(self):
        december = recap.parse_period("2026-12")
        self.assertEqual((december.end, december.last_day), (datetime.date(2027, 1, 1), datetime.date(2026, 12, 31)))

    def test_the_month_before_january_is_december_of_the_year_before(self):
        self.assertEqual(recap.parse_period("2027-01").previous().key, "2026-12")
        self.assertEqual(recap.parse_period("2026-03").previous().key, "2026-02")
        self.assertEqual(recap.parse_period("2026").previous().key, "2025")

    def test_anything_else_is_refused(self):
        for text in ("", "26", "2026-13", "2026-00", "2026-9", "2026-09-01", "abc", "0000", None):
            with self.assertRaises(ValueError, msg=text):
                recap.parse_period(text)


class PlayerStatsTests(unittest.TestCase):
    period = recap.parse_period("2026-09")

    def stats(self, sessions):
        return recap.player_stats(sessions, self.period)

    def test_nothing_played_is_all_zeros(self):
        got = self.stats([])
        self.assertEqual((got["seconds"], got["days"], got["best_streak"], got["star_game_id"], got["best_day"]), (0, 0, 0, None, None))

    def test_the_star_game_is_the_one_with_the_most_time_and_the_smallest_id_wins_a_tie(self):
        sessions = [played(1, "b", D(2026, 9, 1, 10), 2), played(1, "a", D(2026, 9, 2, 10), 1), played(1, "a", D(2026, 9, 3, 10), 1)]
        self.assertEqual(self.stats(sessions)["star_game_id"], "a")

    def test_the_best_day_adds_the_sessions_that_started_on_it(self):
        sessions = [played(1, "a", D(2026, 9, 5, 10), 1), played(1, "b", D(2026, 9, 5, 20), 2), played(1, "a", D(2026, 9, 6, 10), 2)]
        got = self.stats(sessions)
        self.assertEqual((got["best_day"], got["best_day_seconds"]), (datetime.date(2026, 9, 5), 3 * HOUR))

    def test_the_streak_counts_consecutive_days_inside_the_period(self):
        days = [1, 2, 3, 10, 11]
        got = self.stats([played(1, "a", D(2026, 9, day, 10)) for day in days])
        self.assertEqual((got["days"], got["best_streak"]), (5, 3))

    def test_the_totals(self):
        got = self.stats([played(1, "a", D(2026, 9, 1, 10), 1), played(1, "b", D(2026, 9, 1, 12), 3)])
        self.assertEqual((got["seconds"], got["sessions"], got["games"], got["longest_session"]), (4 * HOUR, 2, 2, 3 * HOUR))


class PlaymatesTests(unittest.TestCase):
    def test_only_the_same_game_at_the_same_time_counts(self):
        sessions = [
            played(1, "a", D(2026, 9, 1, 20), 2),
            played(2, "a", D(2026, 9, 1, 21), 2),  # one hour together
            played(3, "b", D(2026, 9, 1, 20), 2),  # another game
            played(3, "a", D(2026, 9, 2, 20), 2),  # another day
        ]
        got = recap.playmates(sessions)
        self.assertEqual(got, {1: (2, HOUR), 2: (1, HOUR)})

    def test_the_one_played_the_most_with_wins_and_the_smallest_id_wins_a_tie(self):
        sessions = [
            played(1, "a", D(2026, 9, 1, 20), 1),
            played(2, "a", D(2026, 9, 1, 20), 1),
            played(3, "a", D(2026, 9, 1, 20), 1),
        ]
        self.assertEqual(recap.playmates(sessions)[1], (2, HOUR))
        self.assertEqual(recap.playmates(sessions)[3], (1, HOUR))

    def test_overlapping_sessions_of_the_same_player_are_not_company(self):
        self.assertEqual(recap.playmates([played(1, "a", D(2026, 9, 1, 20), 2), played(1, "a", D(2026, 9, 1, 21), 2)]), {})

    def test_a_session_inside_a_longer_one_counts_for_its_own_length(self):
        sessions = [played(1, "a", D(2026, 9, 1, 18), 6), played(2, "a", D(2026, 9, 1, 20), 1), played(3, "a", D(2026, 9, 1, 21), 1)]
        self.assertEqual(recap.playmates(sessions)[1], (2, HOUR))


class ActivityStatsTests(unittest.TestCase):
    def test_nothing_played_is_all_zeros(self):
        got = recap.activity_stats([])
        self.assertEqual((got["by_weekday"], got["by_hour"], got["by_day"]), ([0] * 7, [0] * 24, {}))

    def test_the_time_goes_to_the_weekday_hour_and_day_the_session_started_in(self):
        # 2026-09-14 is a Monday; the second session ends after midnight but counts in the Monday
        sessions = [played(1, "a", D(2026, 9, 14, 23), 2), played(1, "b", D(2026, 9, 14, 8), 1), played(1, "a", D(2026, 9, 20, 8), 3)]
        got = recap.activity_stats(sessions)
        self.assertEqual(got["by_weekday"], [3 * HOUR, 0, 0, 0, 0, 0, 3 * HOUR])
        self.assertEqual((got["by_hour"][23], got["by_hour"][8]), (2 * HOUR, 4 * HOUR))
        self.assertEqual(got["by_day"], {"2026-09-14": 3 * HOUR, "2026-09-20": 3 * HOUR})


class GenreAndTopGameTests(unittest.TestCase):
    sessions = [played(1, "a", D(2026, 9, 1, 10), 2), played(1, "b", D(2026, 9, 2, 10), 1), played(1, "c", D(2026, 9, 3, 10), 5)]

    def test_a_game_of_several_genres_counts_in_each_and_one_without_genres_in_none(self):
        genres = {"a": ["RPG", "Action"], "b": ["Action"]}
        self.assertEqual(
            recap.genre_stats(self.sessions, genres),
            [{"genre": "Action", "seconds": 3 * HOUR}, {"genre": "RPG", "seconds": 2 * HOUR}],
        )

    def test_the_genres_are_the_top_five_and_a_tie_goes_by_name(self):
        genres = {"a": ["B", "A", "C", "D", "E", "F"]}
        got = recap.genre_stats([played(1, "a", D(2026, 9, 1, 10))], genres)
        self.assertEqual([g["genre"] for g in got], ["A", "B", "C", "D", "E"])

    def test_the_top_games_have_their_cover_and_the_smallest_id_wins_a_tie(self):
        info = {"c": {"id": "c", "name": "Cee", "image_url": "x.png"}}
        got = recap.top_games(self.sessions, info, limit=2)
        self.assertEqual(got, [{"id": "c", "name": "Cee", "image_url": "x.png", "seconds": 5 * HOUR}, {"id": "a", "name": "a", "image_url": None, "seconds": 2 * HOUR}])


class RarestTests(unittest.TestCase):
    def test_the_fewest_holders_wins_then_the_first_earned(self):
        early = {"id": 1, "title": "A", "holders": 3, "date": datetime.date(2026, 9, 1)}
        late = {"id": 2, "title": "B", "holders": 3, "date": datetime.date(2026, 9, 9)}
        rare = {"id": 3, "title": "C", "holders": 1, "date": datetime.date(2026, 9, 20)}
        self.assertEqual(recap.rarest([late, early])["title"], "A")
        self.assertEqual(recap.rarest([late, early, rare])["title"], "C")
        self.assertIsNone(recap.rarest([]))


class BuildRecapTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        db = self.db
        db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Biel", username="biel", is_active=1),
            models.User(id=3, name="Admin", username=models.GOD_USERNAME, is_active=1),
            models.Game(id="doom", name="Doom", genres="Action, Shooter"),
            models.Game(id="hades", name="Hades", genres="Action"),
            models.PlatformTag(id="pc", name="PC"),
            models.Achievement(id=1, key="common", title="Común", message="", active=True, secret=False, special=0),
            models.Achievement(id=2, key="hidden", title="Oculto", message="", active=True, secret=True, special=0),
        ])
        self.timer(1, "doom", D(2026, 9, 10, 20), 3)
        self.timer(2, "doom", D(2026, 9, 10, 21), 1)
        self.timer(1, "hades", D(2026, 9, 11, 20), 1)
        self.timer(1, "hades", D(2026, 8, 31, 23), 5)  # the month before
        self.timer(1, "doom", D(2026, 10, 1, 0), 5)  # the month after
        self.timer(3, "doom", D(2026, 9, 10, 20), 9)  # the emergency account is not a player
        db.add_all([
            models.UserGame(user_id=1, game_id="doom", platform="pc", started_date=datetime.date(2026, 9, 10), completed=1, completed_date=datetime.date(2026, 9, 25)),
            models.UserGame(user_id=1, game_id="hades", platform="pc", started_date=datetime.date(2026, 8, 31), completed=0),
            models.UserAchievement(user_id=1, achievement_id=1, date=datetime.date(2026, 9, 12)),
            models.UserAchievement(user_id=2, achievement_id=1, date=datetime.date(2026, 9, 12)),
            models.UserAchievement(user_id=1, achievement_id=2, date=datetime.date(2026, 9, 13)),
        ])
        db.commit()

    def timer(self, user, game, start, hours):
        end = start + datetime.timedelta(hours=hours)
        self.db.add(models.GameTimer(user_id=user, game_id=game, start_time=start, end_time=end, duration_seconds=hours * HOUR, is_active=False))

    def build(self, user_id=None, today=datetime.date(2026, 10, 18)):
        return recap.build_recap(self.db, recap.parse_period("2026-09"), user_id, today)

    def test_the_group_counts_only_the_period_and_leaves_out_the_emergency_account(self):
        group = self.build()["group"]
        self.assertEqual((group["seconds"], group["sessions"], group["players"]), (5 * HOUR, 3, 2))
        self.assertEqual([(r["name"], r["seconds"], r["previous_seconds"]) for r in group["ranking"]], [("Ana", 4 * HOUR, 5 * HOUR), ("Biel", HOUR, 0)])
        self.assertEqual(group["previous_seconds"], 5 * HOUR)
        self.assertEqual([(g["name"], g["seconds"], g["players"]) for g in group["top_games"]], [("Doom", 4 * HOUR, 2), ("Hades", HOUR, 1)])

    def test_the_group_does_not_show_secret_achievements(self):
        group = self.build()["group"]
        self.assertEqual(group["achievements"], 2)
        self.assertEqual(group["rarest_achievement"]["title"], "Común")

    def test_the_player_part_is_only_there_when_asked(self):
        self.assertIsNone(self.build()["player"])
        self.assertEqual(self.build(1)["player"]["name"], "Ana")

    def test_when_it_was_played_and_what_kind_of_games(self):
        # 2026-09-10 is a Thursday and the 11th a Friday
        group = self.build()["group"]
        self.assertEqual(group["by_weekday"], [0, 0, 0, 4 * HOUR, HOUR, 0, 0])
        self.assertEqual((group["by_hour"][20], group["by_hour"][21]), (4 * HOUR, HOUR))
        self.assertEqual(group["by_day"], {"2026-09-10": 4 * HOUR, "2026-09-11": HOUR})
        self.assertEqual(group["genres"], [{"genre": "Action", "seconds": 5 * HOUR}, {"genre": "Shooter", "seconds": 4 * HOUR}])
        player = self.build(1)["player"]
        self.assertEqual(player["by_weekday"], [0, 0, 0, 3 * HOUR, HOUR, 0, 0])
        self.assertEqual(player["genres"], [{"genre": "Action", "seconds": 4 * HOUR}, {"genre": "Shooter", "seconds": 3 * HOUR}])
        self.assertEqual([(g["name"], g["seconds"]) for g in player["top_games"]], [("Doom", 3 * HOUR), ("Hades", HOUR)])

    def test_a_player_recap(self):
        player = self.build(1)["player"]
        self.assertEqual((player["seconds"], player["sessions"], player["days"], player["games"], player["position"]), (4 * HOUR, 2, 2, 2, 1))
        self.assertEqual((player["star_game"]["name"], player["star_game"]["seconds"]), ("Doom", 3 * HOUR))
        self.assertEqual(player["best_streak"], 2)
        self.assertEqual(player["playmate"], {"user_id": 2, "name": "Biel", "seconds": HOUR})
        self.assertEqual((player["games_started"], player["games_completed"]), (1, 1))

    def test_the_player_keeps_their_own_secret_achievement_as_the_rarest(self):
        player = self.build(1)["player"]
        self.assertEqual(player["achievements"], 2)
        self.assertEqual(player["rarest_achievement"]["title"], "Oculto")

    def test_a_player_who_did_not_play_has_no_position_and_no_star_game(self):
        self.db.add(models.User(id=4, name="Cris", username="cris", is_active=1))
        self.db.commit()
        player = self.build(4)["player"]
        self.assertEqual((player["seconds"], player["position"], player["star_game"], player["playmate"]), (0, None, None, None))

    def test_a_running_period_is_not_complete(self):
        self.assertTrue(self.build()["complete"])
        self.assertFalse(self.build(today=datetime.date(2026, 9, 30))["complete"])

    def test_a_season_adds_up_its_months(self):
        got = recap.build_recap(self.db, recap.parse_period("2026"), 1, datetime.date(2026, 12, 31))
        self.assertEqual(got["group"]["seconds"], 15 * HOUR)
        self.assertEqual(got["player"]["previous_seconds"], 0)

    def test_an_empty_month_is_all_zeros(self):
        got = recap.build_recap(self.db, recap.parse_period("2026-01"), 1, datetime.date(2026, 10, 18))
        self.assertEqual((got["group"]["seconds"], got["group"]["ranking"], got["group"]["top_games"], got["group"]["rarest_achievement"]), (0, [], [], None))


if __name__ == "__main__":
    unittest.main()
