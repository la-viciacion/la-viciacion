import datetime
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
        return [g["game_name"] for g in games.recommendations_for(self.db, user_id, **kwargs)]

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
        doom = games.recommendations_for(self.db, 1)[0]
        self.assertEqual(doom["players"], ["Bob", "cris"])  # a nameless account shows its username
        self.assertEqual(doom["completed_by"], 1)
        self.assertEqual(doom["genres"], ["Shooter", "Action"])
        self.assertEqual(doom["image_url"], "doom.jpg")

    def test_inactive_players_and_the_emergency_account_recommend_nothing(self):
        add_library(self.db, [(4, "doom", 1), (5, "hades", 1)])
        self.assertEqual(self.names(), [])

    def test_limit(self):
        add_library(self.db, [(2, "doom", 0), (2, "hades", 0), (2, "zelda", 0)])
        self.assertEqual(len(self.names(limit=2)), 2)

    def test_a_user_with_no_library_gets_what_everybody_else_has(self):
        add_library(self.db, [(2, "doom", 0)])
        self.assertEqual(self.names(user_id=3), ["Doom"])


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
