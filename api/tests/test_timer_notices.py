import asyncio
import datetime
import unittest
from unittest import mock

from src.database import models
from src.utils import actions
from tests.sqlite_db import make_session

NOW = datetime.datetime.now()
FIVE = datetime.timedelta(minutes=5)


def add_running(db, user_id, minutes_ago, game_id="g", active=True):
    timer = models.GameTimer(user_id=user_id, game_id=game_id, start_time=NOW - datetime.timedelta(minutes=minutes_ago), is_active=active)
    db.add(timer)
    db.commit()
    return timer


class RefreshTimerNoticesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hollow Knight"))
        self.db.commit()

    def refresh(self, ready=True):
        with mock.patch.object(actions.push, "is_ready", return_value=ready), mock.patch.object(actions.push, "notify_timer", new=mock.AsyncMock()) as notify:
            result = asyncio.run(actions.refresh_timer_notices(self.db, FIVE))
        return result, notify

    def test_every_timer_running_for_five_minutes_is_refreshed(self):
        old = add_running(self.db, 1, 12)
        add_running(self.db, 2, 90)
        result, notify = self.refresh()
        self.assertEqual(result, "2 timers")
        self.assertEqual(notify.await_count, 2)
        notify.assert_any_await(1, "Hollow Knight", old.start_time)

    def test_a_timer_younger_than_the_period_was_announced_when_it_started(self):
        add_running(self.db, 1, 2)
        result, notify = self.refresh()
        self.assertEqual(result, "0 timers")
        notify.assert_not_awaited()

    def test_finished_timers_are_ignored(self):
        add_running(self.db, 1, 60, active=False)
        _, notify = self.refresh()
        notify.assert_not_awaited()

    def test_nothing_happens_while_push_is_not_ready(self):
        add_running(self.db, 1, 60)
        result, notify = self.refresh(ready=False)
        self.assertEqual(result, "")
        notify.assert_not_awaited()


class TimerStopTests(unittest.TestCase):
    def test_unpins_the_notification_with_the_game_name_and_the_duration(self):
        db = make_session()
        db.add(models.Game(id="g", name="Hollow Knight"))
        db.commit()
        with mock.patch("src.database.database.SessionLocal", return_value=db), mock.patch.object(actions.push, "notify_timer_stopped", new=mock.AsyncMock()) as notify:
            actions.after_timer_stop(7, "g", 5100)
        notify.assert_awaited_once_with(7, "Hollow Knight", 5100)


if __name__ == "__main__":
    unittest.main()
