import datetime
import unittest

from sqlalchemy import event

from src.database import models
from src.routers import timers
from tests.sqlite_db import make_session

YEAR = datetime.date.today().year


def session(db, game, day, hours=1, platform="pc", user=1, active=False):
    start = datetime.datetime(YEAR, 3, day, 10)
    db.add(models.GameTimer(
        user_id=user, game_id=game, platform=platform, start_time=start,
        end_time=None if active else start + datetime.timedelta(hours=hours),
        duration_seconds=None if active else hours * 3600, is_active=active,
    ))


class GroupedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([models.Game(id=f"g{i}", name=f"Game {i}", image_url=f"img{i}") for i in range(1, 5)])
        # g1: 4 sessions on two platforms (ps last); g2: 2 sessions; g3: 1; g4: another user's
        for day, platform in ((1, "pc"), (2, "pc"), (3, "ps"), (4, "ps")):
            session(self.db, "g1", day, platform=platform)
        session(self.db, "g2", 5, hours=2)
        session(self.db, "g2", 6, hours=3)
        session(self.db, "g3", 7)
        session(self.db, "g4", 8, user=2)
        session(self.db, "g3", 9, active=True)  # a running timer is not history
        self.db.commit()

    def page(self, **kw):
        args = {"limit": 10, "offset": 0, "sessions_per_game": 10, **kw}
        return timers.get_grouped_timer_history(self.db, 1, **args)

    def test_games_come_newest_first_with_their_totals(self):
        page = self.page()
        self.assertEqual([g.game_id for g in page.groups], ["g3", "g2", "g1"])
        self.assertEqual(page.total_games, 3)
        g2 = page.groups[1]
        self.assertEqual((g2.session_count, g2.total_seconds, g2.game_name, g2.image_url), (2, 5 * 3600, "Game 2", "img2"))

    def test_sessions_are_capped_per_game_newest_first(self):
        g1 = next(g for g in self.page(sessions_per_game=2).groups if g.game_id == "g1")
        self.assertEqual([s.start_time.day for s in g1.sessions], [4, 3])
        self.assertEqual(g1.session_count, 4)  # the count is not capped

    def test_platforms_are_listed_most_recently_used_first(self):
        g1 = next(g for g in self.page().groups if g.game_id == "g1")
        self.assertEqual(g1.platforms, ["ps", "pc"])
        self.assertEqual(g1.platform, "ps")

    def test_only_a_completion_of_the_running_season_is_flagged(self):
        self.db.add_all([
            models.UserGame(user_id=1, game_id="g2", platform="pc", started_date=datetime.date(YEAR - 1, 2, 1), completed=1),
            models.UserGame(user_id=1, game_id="g1", platform="pc", started_date=datetime.date(YEAR, 2, 1), completed=0),
            models.UserGame(user_id=2, game_id="g3", platform="pc", started_date=datetime.date(YEAR, 2, 1), completed=1),
        ])
        self.db.add(models.UserGame(user_id=1, game_id="g1", platform="ps", started_date=datetime.date(YEAR, 3, 1), completed=1))
        self.db.commit()
        self.assertEqual({g.game_id: g.completed for g in self.page().groups}, {"g1": True, "g2": False, "g3": False})

    def test_pagination(self):
        self.assertEqual([g.game_id for g in self.page(limit=1, offset=1).groups], ["g2"])

    def test_a_page_costs_a_fixed_number_of_queries(self):
        queries = []
        event.listen(self.db.get_bind(), "before_cursor_execute", lambda *a: queries.append(a[2]))
        self.page()
        # count, page, games, newest sessions, platforms, completions
        self.assertEqual(len(queries), 6)

    def test_an_empty_history_needs_no_extra_queries(self):
        queries = []
        event.listen(self.db.get_bind(), "before_cursor_execute", lambda *a: queries.append(a[2]))
        page = timers.get_grouped_timer_history(self.db, 99, 10, 0, 10)
        self.assertEqual((page.groups, page.total_games), ([], 0))
        self.assertEqual(len(queries), 2)


if __name__ == "__main__":
    unittest.main()
