import datetime
import unittest
from unittest import mock

from sqlalchemy import event

from src.crud import rankings, users
from src.database import models
from src.routers import statistics
from tests.sqlite_db import make_session
from tests import clock

YEAR = clock.YEAR


class RankingsFromTheDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bob", username="bob", is_active=1),
            models.User(id=3, name="Cris", username="cris", is_active=1),
            models.User(id=4, name="Gone", username="gone", is_active=0),
            models.Game(id="g1", name="Doom"), models.Game(id="g2", name="Quake"), models.Game(id="g3", name="Hades"),
        ])
        start = datetime.date(YEAR, 1, 10)
        entries = [
            (1, "g1", 1), (1, "g2", 1), (1, "g3", 0),      # Ana: 3 entries, 2 completed
            (2, "g1", 0), (2, "g2", 0),                    # Bob: 2 entries, none completed
            (4, "g1", 1),                                  # inactive: listed like the rest
        ]
        for user_id, game_id, completed in entries:
            self.db.add(models.UserGame(user_id=user_id, game_id=game_id, completed=completed, started_date=start, platform="pc"))
        self.db.add(models.UserGame(user_id=1, game_id="g1", completed=1, started_date=datetime.date(YEAR - 1, 5, 1), platform="ps"))
        self.db.commit()

    def test_counts_cover_every_player_for_the_season_only(self):
        counts = {c["user_id"]: (c["entries"], c["completed"]) for c in rankings.library_counts(self.db)}
        self.assertEqual(counts, {1: (3, 2), 2: (2, 0), 3: (0, 0), 4: (1, 1)})

    def test_another_season_is_counted_on_its_own(self):
        counts = {c["user_id"]: (c["entries"], c["completed"]) for c in rankings.library_counts(self.db, YEAR - 1)}
        self.assertEqual(counts[1], (1, 1))

    def test_completed_games_ranking(self):
        got = rankings.user_completed_games(self.db)
        self.assertEqual([(r["user_id"], r["completed_games"]) for r in got], [(1, 2), (4, 1), (2, 0), (3, 0)])

    def test_ratio_ranking_rounds_and_puts_zeros_last_by_id(self):
        got = rankings.user_ratio(self.db)
        self.assertEqual([(r["user_id"], r["ratio"]) for r in got], [(4, 1.0), (1, 0.67), (2, 0), (3, 0)])

    def test_only_active_leaves_out_inactive_players_everywhere(self):
        for ranking in (
            rankings.user_completed_games(self.db, is_active=True),
            rankings.user_ratio(self.db, is_active=True),
            rankings.user_days_played(self.db, is_active=True),
            rankings.user_hours_players(self.db, is_active=True),
            rankings.user_played_games(self.db, is_active=True),
            rankings.user_current_streak(self.db, is_active=True),
            rankings.user_best_streak(self.db, is_active=True),
        ):
            self.assertNotIn(4, [dict(getattr(r, "_mapping", r))["user_id"] for r in ranking])

    def test_each_ranking_is_one_query_not_one_per_player(self):
        queries = []
        event.listen(self.db.get_bind(), "before_cursor_execute", lambda *a: queries.append(a[2]))
        rankings.user_completed_games(self.db)
        self.assertEqual(len(queries), 1)
        rankings.user_ratio(self.db)
        self.assertEqual(len(queries), 2)


class SharedDataTests(unittest.TestCase):
    def test_days_and_counts_are_computed_once_per_request(self):
        with mock.patch.object(statistics.rankings, "players_with_dates", return_value=[]) as days, \
                mock.patch.object(statistics.rankings, "library_counts", return_value=[]) as counts:
            shared = statistics._SharedRankingData(mock.MagicMock())
            for _ in range(3):
                shared.players
                shared.counts
        days.assert_called_once()
        counts.assert_called_once()

    def test_nothing_is_computed_if_no_ranking_needs_it(self):
        with mock.patch.object(statistics.rankings, "players_with_dates") as days:
            statistics._SharedRankingData(mock.MagicMock())
        days.assert_not_called()


class GamesLastPlayedTests(unittest.TestCase):
    def test_each_game_once_newest_first_and_limited(self):
        db = make_session()
        db.add(models.User(id=1, name="Ana", username="ana", is_active=1))
        db.add_all([models.Game(id=f"g{i}", name=f"Game {i}") for i in range(4)])
        for day, game in ((1, "g0"), (2, "g1"), (3, "g0"), (4, "g2"), (5, "g3")):
            db.add(models.GameTimer(
                user_id=1, game_id=game, start_time=datetime.datetime(YEAR, 3, day, 10), end_time=datetime.datetime(YEAR, 3, day, 11),
                duration_seconds=3600, is_active=False,
            ))
        db.commit()
        got = rankings.games_last_played(db, limit=3)
        self.assertEqual([g["game_id"] for g in got], ["g3", "g2", "g0"])
        self.assertEqual(got[2]["start"], datetime.datetime(YEAR, 3, 3, 10))


class EmergencyAccountTests(unittest.TestCase):
    """The "admin" account is a door, not a player: it is in no ranking and no list of players."""

    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Dios", username="admin", is_active=1, is_admin=1),
            models.Game(id="g1", name="Doom"), models.Game(id="g2", name="Quake"),
            models.PlatformTag(id="pc", name="PC"),
        ])
        day = datetime.date(YEAR, 1, 10)
        for user_id, game_id in ((1, "g1"), (2, "g1"), (2, "g2")):
            self.db.add(models.UserGame(user_id=user_id, game_id=game_id, completed=1, started_date=day, platform="pc"))
            self.db.add(models.GameTimer(
                user_id=user_id, game_id=game_id, start_time=datetime.datetime(YEAR, 1, 10, 10),
                end_time=datetime.datetime(YEAR, 1, 10, 11), duration_seconds=3600, is_active=False,
            ))
        self.db.commit()

    def ids(self, rows):
        return [r["user_id"] for r in (dict(getattr(r, "_mapping", r)) for r in rows)]

    def test_rankings_by_player_leave_it_out(self):
        # streaks share the query of the days ranking (players_played_dates), so days covers them
        for ranking in (
            rankings.user_hours_players(self.db),
            rankings.user_days_played(self.db),
            rankings.user_played_games(self.db),
            rankings.user_completed_games(self.db),
            rankings.user_ratio(self.db),
        ):
            self.assertEqual(self.ids(ranking), [1])

    def test_rankings_by_game_ignore_its_sessions(self):
        self.assertEqual([g["game_id"] for g in rankings.games_most_played(self.db)], ["g1"])
        self.assertEqual([g["game_id"] for g in rankings.games_last_played(self.db)], ["g1"])
        self.assertEqual([row[2] for row in rankings.platform_played_games(self.db)], [1])

    def test_list_of_players_leaves_it_out(self):
        self.assertEqual([u.username for u in users.get_users(self.db)], ["ana"])


if __name__ == "__main__":
    unittest.main()
