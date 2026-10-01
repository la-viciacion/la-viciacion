"""What happens when a timer stops: the rankings are recomputed from the sessions and, if the notices
are on, the changes reach the group. Real queries on an in-memory database; only the outgoing edges
(Telegram, push, the AI) and the settings are replaced."""
import datetime
import unittest
from unittest import mock

from fastapi import BackgroundTasks
from sqlalchemy.orm import sessionmaker

from src.utils import actions  # first: it breaks an import cycle between crud and utils
from src.database import models
from src.routers import timers
from src.utils import my_utils, push
from tests.sqlite_db import make_session

GROUP = "-100123"
ON = {
    "notifications.enabled": True,
    "telegram.token": "123456:" + "a" * 30,
    "telegram.group_id": GROUP,
}


class StoppingATimerTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.factory = sessionmaker(bind=self.db.get_bind(), autoflush=False)
        now = datetime.datetime.now()
        self.db.add_all([
            models.User(id=1, name="Ana", username="ana", is_active=1, is_admin=0),
            models.User(id=2, name="Bob", username="bob", is_active=1, is_admin=0),
            models.Game(id="g1", name="Doom"),
            models.Game(id="g2", name="Quake"),
            # Ana: 1 hour of Doom. Bob: half an hour of Quake and a timer that is still running.
            models.GameTimer(user_id=1, game_id="g1", start_time=now - datetime.timedelta(hours=5),
                             end_time=now - datetime.timedelta(hours=4), duration_seconds=3600, is_active=False),
            models.GameTimer(user_id=2, game_id="g2", start_time=now - datetime.timedelta(hours=5),
                             end_time=now - datetime.timedelta(hours=4, minutes=30), duration_seconds=1800, is_active=False),
        ])
        self.db.commit()
        self.running = models.GameTimer(user_id=2, game_id="g2", start_time=now - datetime.timedelta(hours=2), is_active=True)
        self.db.add(self.running)
        self.db.commit()

    def stop(self, owner=2):
        """Stop the running timer through the endpoint and run the background tasks it scheduled."""
        background = BackgroundTasks()
        user = self.db.get(models.User, owner)
        timers.stop_timer_endpoint(self.running.id, owner, background, current_user=user, db=self.db)
        return background

    def run_background(self, background, settings=ON, push_ready=False, telegram_fails=False):
        """Run the scheduled tasks like Starlette would; returns (messages sent to Telegram, push notices, checks)."""
        bot = mock.MagicMock()
        bot.send_message = mock.AsyncMock(side_effect=RuntimeError("telegram down") if telegram_fails else None)
        pushed = mock.AsyncMock()
        checks = mock.AsyncMock()
        patches = [
            mock.patch("src.database.database.SessionLocal", self.factory),
            mock.patch.object(my_utils.settings, "get", side_effect=lambda key: settings.get(key)),
            mock.patch.object(my_utils.telegram, "Bot", return_value=bot),
            mock.patch.object(my_utils.ai, "is_ready", return_value=False),
            mock.patch.object(push, "is_ready", return_value=push_ready),
            mock.patch.object(push, "notify_group", pushed),
            mock.patch.object(actions, "check_users", checks),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for task in background.tasks:
            task.func(*task.args, **task.kwargs)
        sent = [call.kwargs["text"] for call in bot.send_message.await_args_list]
        return sent, [call.args[0] for call in pushed.await_args_list], checks

    def test_stopping_schedules_the_checks_with_the_ranking_from_before(self):
        background = self.stop()
        self.assertEqual(len(background.tasks), 1)
        task = background.tasks[0]
        self.assertIs(task.func, actions.after_session_change)
        user_id, silent, before = task.args
        self.assertEqual((user_id, silent), (2, False))
        self.assertEqual(before, {"players": [1, 2], "games": ["g1", "g2"]})  # a running timer counts for nothing yet

    def test_an_overtaking_is_announced_to_the_group_with_the_new_totals(self):
        sent, _, checks = self.run_background(self.stop())
        self.assertEqual(len(sent), 2)
        games, players = sent
        self.assertIn("ránking de juegos", games)
        self.assertIn("1. ⬆️ *Quake*: 02h30m (↑1)", games)
        self.assertIn("2. ⬇️ *Doom*: 01h00m (↓1)", games)
        self.assertIn("ránking de horas", players)
        self.assertIn("1. ⬆️ *Bob*: 02h30m (↑1)", players)
        self.assertIn("2. ⬇️ *Ana*: 01h00m (↓1)", players)
        checks.assert_awaited_once()
        self.assertEqual(checks.await_args.kwargs["user_ids"], [2])

    def test_every_message_goes_to_the_group(self):
        bot_chat_ids = []
        with mock.patch.object(my_utils, "_telegram_send", new=mock.AsyncMock(side_effect=lambda bot, chat, text, image=None: bot_chat_ids.append(chat) or True)):
            self.run_background(self.stop())
        self.assertEqual(bot_chat_ids, [GROUP, GROUP])

    def test_nothing_is_announced_when_the_order_does_not_change(self):
        # Bob's timer is short: he stays second and Quake stays second
        self.running.start_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        self.db.commit()
        sent, _, checks = self.run_background(self.stop())
        self.assertEqual(sent, [])
        checks.assert_awaited_once()  # the achievements are checked anyway

    def test_a_player_who_already_led_does_not_announce_extending_the_lead(self):
        self.running.user_id = 1
        self.running.game_id = "g1"
        self.db.commit()
        sent, _, _ = self.run_background(self.stop(owner=1))
        self.assertEqual(sent, [])

    def test_notifications_off_send_nothing_but_the_checks_still_run(self):
        sent, pushed, checks = self.run_background(self.stop(), settings={**ON, "notifications.enabled": False})
        self.assertEqual((sent, pushed), ([], []))
        checks.assert_awaited_once()

    def test_without_telegram_the_devices_still_get_the_notice(self):
        sent, pushed, _ = self.run_background(self.stop(), settings={"notifications.enabled": True}, push_ready=True)
        self.assertEqual(sent, [])
        self.assertEqual(len(pushed), 2)
        self.assertIn("ránking de horas", pushed[1])

    def test_nothing_configured_sends_nothing(self):
        sent, pushed, _ = self.run_background(self.stop(), settings={"notifications.enabled": True})
        self.assertEqual((sent, pushed), ([], []))

    def test_telegram_failing_does_not_break_the_follow_up(self):
        _, _, checks = self.run_background(self.stop(), telegram_fails=True)  # does not raise
        checks.assert_awaited_once()

    def test_a_session_edited_by_hand_is_silent(self):
        before = actions.ranking_snapshot(self.db)
        self.running.start_time = datetime.datetime.now() - datetime.timedelta(hours=3)
        self.db.commit()
        timers.stop_timer(self.db, self.running.id, 2)
        background = BackgroundTasks()
        background.add_task(actions.after_session_change, 2, True, before)  # what the manual/edit routes schedule
        sent, pushed, checks = self.run_background(background)
        self.assertEqual((sent, pushed), ([], []))
        checks.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
