import datetime
import random
import unittest
from unittest import mock

from src.crud import games
from src.database import models
from src.utils import my_utils
from tests.sqlite_db import make_session

DAY = datetime.date(datetime.date.today().year, 1, 10)


def add_library(db, rows):
    for user_id, game_id, completed in rows:
        db.add(models.UserGame(user_id=user_id, game_id=game_id, completed=completed, started_date=DAY, platform="pc"))
    db.commit()


class RecommendationsForTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bob", username="bob", is_active=1),
            models.User(id=3, name=None, username="cris", is_active=1),
            models.User(id=4, name="Gone", username="gone", is_active=0),
            models.User(id=5, name="Dios", username="admin", is_active=1, is_admin=1),
            models.Game(id="doom", name="Doom", genres="Shooter, Action", image_url="doom.jpg"),
            models.Game(id="hades", name="Hades", genres="Action"),
            models.Game(id="zelda", name="Zelda", genres=None),
            models.Game(id="quake", name="Quake"),
            models.Game(id="mine", name="Minecraft"),
        ])
        self.db.commit()

    def names(self, user_id=1, **kwargs):
        return [g["game_name"] for g in games.recommendation_candidates(self.db, user_id, **kwargs)]

    def test_games_the_user_already_has_are_left_out_whatever_the_season(self):
        add_library(self.db, [(1, "doom", 0), (2, "doom", 0), (2, "hades", 0)])
        self.db.add(models.UserGame(user_id=1, game_id="hades", completed=1, started_date=datetime.date(2020, 3, 1), platform="pc"))
        self.db.commit()
        self.assertEqual(self.names(), [])

    def test_most_shared_first_then_most_completed_then_name(self):
        add_library(self.db, [
            (2, "hades", 0), (3, "hades", 0),                      # 2 players
            (2, "zelda", 1), (3, "zelda", 1),                      # 2 players, both completed it
            (2, "mine", 0), (3, "quake", 0), (2, "quake", 0),      # quake: 2 players, none completed
            (3, "doom", 0),                                        # 1 player
        ])
        self.assertEqual(self.names(), ["Zelda", "Hades", "Quake", "Doom", "Minecraft"])

    def test_the_game_lists_its_players_once_and_who_completed_it(self):
        add_library(self.db, [(2, "doom", 1), (3, "doom", 0)])
        self.db.add(models.UserGame(user_id=2, game_id="doom", completed=0, started_date=datetime.date(2020, 3, 1), platform="ps"))
        self.db.commit()
        doom = games.recommendation_candidates(self.db, 1)[0]
        self.assertEqual(doom["players"], ["Bob", "cris"])  # a nameless account shows its username
        self.assertEqual(doom["completed_by"], 1)
        self.assertEqual(doom["genres"], ["Shooter", "Action"])
        self.assertEqual(doom["image_url"], "doom.jpg")

    def test_inactive_players_and_the_emergency_account_recommend_nothing(self):
        add_library(self.db, [(4, "doom", 1), (5, "hades", 1)])
        self.assertEqual(self.names(), [])

    def test_limit_picks_that_many_of_the_candidates_keeping_their_order(self):
        add_library(self.db, [(2, "doom", 0), (3, "doom", 0), (2, "hades", 0), (2, "zelda", 0), (2, "quake", 0)])
        everything = self.names()
        for seed in range(20):
            picked = [g["game_name"] for g in games.recommendations_for(self.db, 1, limit=2, rng=random.Random(seed))]
            self.assertEqual(len(picked), 2)
            self.assertEqual(picked, sorted(picked, key=everything.index))

    def test_every_visit_can_show_other_games(self):
        add_library(self.db, [(2, "doom", 0), (2, "hades", 0), (2, "zelda", 0), (2, "quake", 0), (2, "mine", 0)])
        seen = {
            frozenset(g["game_name"] for g in games.recommendations_for(self.db, 1, limit=2, rng=random.Random(seed)))
            for seed in range(30)
        }
        self.assertGreater(len(seen), 1)

    def test_fewer_candidates_than_the_limit_are_all_returned(self):
        add_library(self.db, [(2, "doom", 0)])
        self.assertEqual([g["game_name"] for g in games.recommendations_for(self.db, 1, limit=12)], ["Doom"])

    def test_a_user_with_no_library_gets_what_everybody_else_has(self):
        add_library(self.db, [(2, "doom", 0)])
        self.assertEqual(self.names(user_id=3), ["Doom"])


def add_session(db, user_id, game_id, hours, day=1):
    start = datetime.datetime(DAY.year, 2, day, 10)
    db.add(models.GameTimer(
        user_id=user_id, game_id=game_id, platform="pc", start_time=start,
        end_time=start + datetime.timedelta(hours=hours), duration_seconds=hours * 3600, is_active=False,
    ))
    db.commit()


class WeightTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1),
            models.User(id=2, name="Bob", username="bob", is_active=1),
            models.User(id=3, name="Cris", username="cris", is_active=1),
            models.User(id=4, name="Gone", username="gone", is_active=0),
            models.Game(id="doom", name="Doom", genres="Shooter"),
            models.Game(id="hades", name="Hades", genres="Roguelike"),
            models.Game(id="zelda", name="Zelda", genres="Adventure"),
        ])
        self.db.commit()

    def item(self, **kw):
        return {"players": ["Bob"], "completed_by": 0, "played_seconds": 0, "sessions": 0, "genres": [], **kw}

    def test_candidates_carry_what_the_others_played_but_not_the_users_nor_inactive_players(self):
        add_library(self.db, [(2, "doom", 0), (3, "doom", 0), (4, "doom", 0)])
        add_session(self.db, 2, "doom", 2, day=1)
        add_session(self.db, 3, "doom", 3, day=2)
        add_session(self.db, 4, "doom", 50, day=3)  # inactive: not counted
        add_session(self.db, 1, "doom", 40, day=4)  # the user's own time is not "what the others played"
        doom = games.recommendation_candidates(self.db, 1)[0]
        self.assertEqual((doom["played_seconds"], doom["sessions"]), (5 * 3600, 2))

    def test_every_signal_raises_the_weight(self):
        base = games.recommendation_weight(self.item(), {})
        for change in ({"players": ["Bob", "Cris"]}, {"completed_by": 1}, {"played_seconds": 3600}, {"sessions": 1}):
            self.assertGreater(games.recommendation_weight(self.item(**change), {}), base, change)

    def test_hours_and_sessions_are_damped(self):
        some = games.recommendation_weight(self.item(played_seconds=10 * 3600, sessions=10), {})
        lots = games.recommendation_weight(self.item(played_seconds=1000 * 3600, sessions=1000), {})
        self.assertLess(lots, 4 * some)

    def test_the_genres_the_user_plays_most_boost_the_weight_up_to_double(self):
        add_session(self.db, 1, "doom", 9)
        add_session(self.db, 1, "hades", 1, day=2)
        affinity = games.genre_affinity(self.db, 1)
        self.assertAlmostEqual(affinity["shooter"], 0.9)
        liked = games.recommendation_weight(self.item(genres=["Shooter"]), affinity)
        other = games.recommendation_weight(self.item(genres=["Adventure"]), affinity)
        self.assertGreater(liked, other)
        self.assertLessEqual(liked, 2 * other)

    def test_a_user_with_no_sessions_has_no_affinity(self):
        self.assertEqual(games.genre_affinity(self.db, 1), {})

    def test_the_sample_has_no_repeats_and_favours_the_heavy(self):
        weights = [1, 1, 1, 1, 50]
        counts = [0] * 5
        for seed in range(200):
            picked = games.weighted_sample(weights, 2, random.Random(seed))
            self.assertEqual(len(set(picked)), 2)
            for i in picked:
                counts[i] += 1
        self.assertGreater(counts[4], 190)
        self.assertTrue(all(c > 0 for c in counts[:4]))  # the light ones still come out now and then


class FakeBot:
    sent = []

    def __init__(self, token):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, **kwargs):
        FakeBot.sent.append(kwargs)


class CompletionNoticeTests(unittest.IsolatedAsyncioTestCase):
    values = {
        "notifications.enabled": True,
        "telegram.token": "123456789:AAE_abcdefghijklmnopqrstuvwxyz012345",
        "telegram.group_id": "-100",
    }

    async def send(self, recommended, completion):
        FakeBot.sent = []
        chat = mock.Mock(return_value=completion)
        with mock.patch.object(my_utils.telegram, "Bot", FakeBot), \
                mock.patch.object(my_utils.settings, "get", side_effect=lambda k: self.values.get(k, my_utils.settings.REGISTRY[k].default)), \
                mock.patch.object(my_utils.ai, "is_ready", return_value=True), \
                mock.patch.object(my_utils.ai, "complete", chat):
            await my_utils.send_message("Ana completó Doom", False, ai_use="completed_game", new_game_recommended=recommended)
        return chat, FakeBot.sent[0]["text"]

    async def test_without_ai_the_recommendation_is_a_plain_line(self):
        _, text = await self.send({"game": "Half_Life", "user": "Bob"}, completion=None)
        self.assertTrue(text.startswith("Ana completó Doom"))
        self.assertIn("Half\_Life", text)  # escaped: a name must not break the Markdown
        self.assertIn("Lo tiene Bob", text)

    async def test_the_ai_is_told_about_the_recommendation_and_the_line_is_not_added(self):
        chat, text = await self.send({"game": "Hades", "user": "Bob"}, completion="Qué crack, Ana. Prueba Hades")
        self.assertEqual(text, "Qué crack, Ana. Prueba Hades")
        prompt = chat.call_args.args[0]
        self.assertIn("Juego recomendado: Hades", prompt)
        self.assertIn("Jugado por: Bob", prompt)

    async def test_nothing_to_recommend_leaves_the_notice_alone(self):
        for recommended in (None, {}):
            _, text = await self.send(recommended, completion=None)
            self.assertEqual(text, "Ana completó Doom")


if __name__ == "__main__":
    unittest.main()
