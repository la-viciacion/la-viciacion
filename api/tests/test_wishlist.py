import datetime
import unittest
from unittest import mock

from src.crud import wishlist
from src.database import models
from src.utils import actions, rawg_sync
from tests.sqlite_db import make_session

TODAY = datetime.date(2026, 10, 4)
D = datetime.date


class UpcomingTests(unittest.TestCase):
    def test_a_game_without_a_date_or_with_a_future_one_is_upcoming(self):
        self.assertTrue(wishlist.is_upcoming(None, TODAY))
        self.assertTrue(wishlist.is_upcoming(D(2026, 10, 5), TODAY))
        self.assertFalse(wishlist.is_upcoming(TODAY, TODAY))
        self.assertFalse(wishlist.is_upcoming(D(2020, 1, 1), TODAY))

    def test_days_until_counts_from_today_and_not_for_what_is_out(self):
        self.assertEqual(wishlist.days_until(D(2026, 10, 14), TODAY), 10)
        self.assertEqual(wishlist.days_until(TODAY, TODAY), 0)
        self.assertIsNone(wishlist.days_until(D(2026, 10, 3), TODAY))
        self.assertIsNone(wishlist.days_until(None, TODAY))


class WishlistQueryTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, username="ana", name="Ana", is_active=1),
            models.User(id=2, username="bea", name="Bea", is_active=1),
            models.User(id=3, username="gone", name="Gone", is_active=0),
            models.Game(id="soon", name="Soon", release_date=D(2026, 12, 1), rawg_id=1),
            models.Game(id="later", name="Later", release_date=D(2027, 3, 1), rawg_id=2),
            models.Game(id="tba", name="Tba", release_date=None, rawg_id=3),
            models.Game(id="out", name="Out", release_date=D(2020, 1, 1), rawg_id=4),
            models.Game(id="today", name="Today", release_date=TODAY, rawg_id=5),
        ])
        self.db.commit()

    def wish(self, user_id, game_id, added=None):
        self.db.add(models.UserWishlist(user_id=user_id, game_id=game_id, added_at=added or datetime.datetime(2026, 10, 1)))
        self.db.commit()

    def test_it_splits_the_list_into_upcoming_by_date_and_wanted_by_latest_wish(self):
        for game in ("later", "tba", "soon"):
            self.wish(1, game)
        self.wish(1, "out", datetime.datetime(2026, 9, 1))
        self.wish(1, "today", datetime.datetime(2026, 9, 20))
        body = wishlist.wishlist(self.db, 1, TODAY)
        self.assertEqual([g["id"] for g in body["upcoming"]], ["soon", "later", "tba"])
        self.assertEqual([g["id"] for g in body["wanted"]], ["today", "out"])
        self.assertEqual(body["upcoming"][0]["days_until"], 58)

    def test_a_game_that_is_in_the_library_leaves_the_list_by_itself(self):
        self.wish(1, "out")
        self.db.add(models.UserGame(user_id=1, game_id="out", started_date=TODAY, platform=None))
        self.db.commit()
        self.assertEqual(wishlist.wishlist(self.db, 1, TODAY), {"upcoming": [], "wanted": []})
        self.assertEqual(wishlist.wished_ids(self.db, 1), set())

    def test_it_says_who_else_wants_a_game_but_not_inactive_players_nor_the_viewer(self):
        for user in (1, 2, 3):
            self.wish(user, "soon")
        item = wishlist.wishlist(self.db, 1, TODAY)["upcoming"][0]
        self.assertEqual([w["name"] for w in item["wanted_by"]], ["Bea"])

    def test_adding_twice_keeps_one_wish_and_removing_nothing_is_fine(self):
        wishlist.add(self.db, 1, "soon")
        self.db.commit()
        wishlist.add(self.db, 1, "soon")
        self.db.commit()
        self.assertEqual(self.db.query(models.UserWishlist).count(), 1)
        wishlist.remove(self.db, 1, "later")
        wishlist.remove(self.db, 1, "soon")
        self.db.commit()
        self.assertEqual(self.db.query(models.UserWishlist).count(), 0)

    def test_only_games_that_are_not_out_and_known_to_rawg_are_refreshed(self):
        self.db.add(models.Game(id="nolink", name="No link", release_date=None, rawg_id=None))
        self.db.commit()
        for game in ("soon", "tba", "out", "today", "nolink"):
            self.wish(1, game)
        self.assertEqual({g.id for g in wishlist.to_refresh(self.db, TODAY)}, {"soon", "tba", "today"})

    def test_a_game_nobody_still_waits_for_is_not_refreshed(self):
        self.wish(3, "soon")  # an inactive player
        self.wish(2, "later")
        self.db.add(models.UserGame(user_id=2, game_id="later", started_date=TODAY, platform=None))
        self.db.commit()
        self.assertEqual(wishlist.to_refresh(self.db, TODAY), [])

    def test_releases_on_a_day_name_who_waits_and_who_else_does(self):
        self.wish(1, "today")
        self.wish(2, "today")
        self.wish(3, "today")
        self.wish(1, "soon")
        found = wishlist.releases_on(self.db, TODAY)
        self.assertEqual([(u.username, g.id, [w["name"] for w in others]) for u, g, others in found],
                         [("ana", "today", ["Bea"]), ("bea", "today", ["Ana"])])


class ReleaseNoticeTests(unittest.TestCase):
    def test_names_are_joined_in_spanish(self):
        self.assertEqual(actions.join_names(["Ana"]), "Ana")
        self.assertEqual(actions.join_names(["Ana", "Bea"]), "Ana y Bea")
        self.assertEqual(actions.join_names(["Ana", "Bea", "Cai"]), "Ana, Bea y Cai")

    def test_the_notice_says_who_else_waits_for_each_game(self):
        message = actions.wishlist_release_message([("Hades II", ["Bea"]), ("Celeste", []), ("Hollow", ["Bea", "Cai"])])
        self.assertEqual(message, (
            "¡Hoy sale *Hades II*! Estaba en tu lista de deseados.\nTambién lo espera Bea.\n\n"
            "¡Hoy sale *Celeste*! Estaba en tu lista de deseados.\n\n"
            "¡Hoy sale *Hollow*! Estaba en tu lista de deseados.\nTambién lo esperan Bea y Cai."
        ))

    def test_markdown_in_a_name_is_escaped(self):
        self.assertIn("*Snake\\_Pass*", actions.wishlist_release_message([("Snake_Pass", [])]))


class EveNoticeTests(unittest.TestCase):
    def test_the_group_notice_names_each_game_and_who_waits_for_it(self):
        message = actions.wishlist_eve_message([("Hades II", ["Ana"]), ("Snake_Pass", ["Ana", "Bea", "Cai"])])
        self.assertEqual(message, (
            "Mañana sale *Hades II*. Está en la lista de deseados de Ana.\n\n"
            "Mañana sale *Snake\\_Pass*. Está en la lista de deseados de Ana, Bea y Cai."
        ))

    def test_the_wished_releases_of_a_day_are_grouped_by_game(self):
        db = make_session()
        tomorrow = TODAY + datetime.timedelta(days=1)
        db.add_all([
            models.User(id=1, username="ana", name="Ana", is_active=1),
            models.User(id=2, username="bea", name="Bea", is_active=1),
            models.User(id=3, username="gone", name="Gone", is_active=0),
            models.Game(id="b", name="Bravo", release_date=tomorrow, rawg_id=1),
            models.Game(id="a", name="alpha", release_date=tomorrow, rawg_id=2),
            models.Game(id="c", name="Charlie", release_date=tomorrow, rawg_id=3),
            models.Game(id="d", name="Delta", release_date=TODAY, rawg_id=4),
        ])
        db.commit()
        for user_id, game_id in ((1, "b"), (2, "b"), (2, "a"), (3, "c"), (1, "d")):
            wishlist.add(db, user_id, game_id)
        db.commit()
        found = wishlist.wished_releases_on(db, tomorrow)
        self.assertEqual([(g.id, names) for g, names in found], [("a", ["Bea"]), ("b", ["Ana", "Bea"])])


class RefreshReleaseDatesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.Game(id="a", name="A", release_date=D(2026, 12, 1), rawg_id=1),
            models.Game(id="b", name="B", release_date=None, rawg_id=2),
            models.Game(id="c", name="C", release_date=D(2026, 12, 1), rawg_id=3),
        ])
        self.db.commit()

    def refresh(self, answers, max_calls=50, key="k"):
        def get(client, path, **__):
            client.calls += 1  # what the real client does, so the budget is spent
            answer = answers[path]
            if isinstance(answer, Exception):
                raise answer
            return answer

        games = self.db.query(models.Game).order_by(models.Game.id).all()
        with mock.patch.object(type(rawg_sync.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value=key), \
                mock.patch.object(rawg_sync._Client, "get", get):
            return rawg_sync.refresh_release_dates(self.db, games, max_calls)

    def dates(self):
        return {g.id: g.release_date for g in self.db.query(models.Game)}

    def test_a_new_date_is_written_and_a_missing_one_is_never_blanked(self):
        changed = self.refresh({"/games/1": {"released": "2027-02-02"}, "/games/2": {"released": "2026-11-11"}, "/games/3": {"released": None}})
        self.assertEqual([g.id for g in changed], ["a", "b"])
        self.assertEqual(self.dates(), {"a": D(2027, 2, 2), "b": D(2026, 11, 11), "c": D(2026, 12, 1)})

    def test_an_unchanged_date_is_not_reported(self):
        self.assertEqual(self.refresh({"/games/1": {"released": "2026-12-01"}, "/games/2": {}, "/games/3": {"released": "garbage"}}), [])

    def test_a_failed_game_does_not_stop_the_others_but_a_refused_key_does(self):
        changed = self.refresh({"/games/1": ConnectionError("boom"), "/games/2": {"released": "2026-11-11"}, "/games/3": {"released": "2027-01-01"}})
        self.assertEqual([g.id for g in changed], ["b", "c"])
        changed = self.refresh({"/games/1": {"released": "2030-01-01"}, "/games/2": rawg_sync.RawgFatal("quota"), "/games/3": {"released": "2031-01-01"}})
        self.assertEqual([g.id for g in changed], ["a"])

    def test_it_respects_the_call_budget_and_needs_a_key(self):
        changed = self.refresh({f"/games/{i}": {"released": "2030-01-01"} for i in (1, 2, 3)}, max_calls=2)
        self.assertEqual(len(changed), 2)
        self.assertEqual(self.refresh({}, key=""), [])


if __name__ == "__main__":
    unittest.main()
