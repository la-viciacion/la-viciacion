import datetime
import unittest

from src.database import models
from src.routers import manage
from tests.sqlite_db import make_session


class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        now = datetime.datetime.now()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1, telegram_id=11),
            models.User(id=2, name="Beto", username="beto", is_active=1),
            models.User(id=3, name="Cris", username="cris", is_active=0),
            models.User(id=4, name="Dios", username=models.GOD_USERNAME, is_active=1),
            models.Game(id="a", name="Doom", rawg_id=1),
            models.Game(id="b", name="Quake"),
        ])
        self.db.add_all([
            models.GameTimer(user_id=1, game_id="a", start_time=now - datetime.timedelta(hours=30), is_active=True),
            models.GameTimer(user_id=2, game_id="b", start_time=now - datetime.timedelta(hours=1), is_active=True),
            models.GameTimer(user_id=2, game_id="a", start_time=now - datetime.timedelta(hours=40), end_time=now, duration_seconds=1, is_active=False),
        ])
        self.db.commit()

    def test_only_running_timers_older_than_the_threshold_count(self):
        got = manage.attention(self.db)
        self.assertEqual(got["stale_timers"], 1)
        self.assertEqual([(t["user"], t["game"]) for t in got["stale_timers_oldest"]], [("ana", "Doom")])

    def test_players_without_telegram_leave_out_inactive_users_and_the_god_account(self):
        self.assertEqual(manage.attention(self.db)["users_without_telegram"], 1)

    def test_games_without_rawg(self):
        self.assertEqual(manage.attention(self.db)["games_without_rawg"], 1)
