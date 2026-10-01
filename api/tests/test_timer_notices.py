import asyncio
import datetime
import unittest
from unittest import mock

from src.database import models
from src.utils import actions, user_settings
from tests.sqlite_db import make_session

D = datetime.datetime
SLOT = D(2026, 10, 1, 20, 40)  # a whole minute, like the scheduler's slots


def started(minutes_before):
    return SLOT - datetime.timedelta(minutes=minutes_before)


def add_running(db, user_id, start, game_id="g", active=True):
    timer = models.GameTimer(user_id=user_id, game_id=game_id, start_time=start, is_active=active)
    db.add(timer)
    db.commit()
    return timer


class TimerNoticeDueTests(unittest.TestCase):
    def test_due_once_per_interval_of_play(self):
        for minutes, due in ((0, False), (5, False), (9, False), (10, True), (11, False), (19, False), (20, True), (30, True), (35, False)):
            self.assertEqual(actions.timer_notice_due(SLOT, started(minutes), 10), due, minutes)

    def test_each_user_has_their_own_interval(self):
        self.assertTrue(actions.timer_notice_due(SLOT, started(30), 15))
        self.assertFalse(actions.timer_notice_due(SLOT, started(20), 15))
        self.assertTrue(actions.timer_notice_due(SLOT, started(60), 60))

    def test_the_seconds_of_the_start_do_not_matter(self):
        # started at 20:30:10 and at 20:30:50: both are 10 minutes old at the 20:40 slot, by their minute
        self.assertTrue(actions.timer_notice_due(SLOT, D(2026, 10, 1, 20, 30, 10), 10))
        self.assertTrue(actions.timer_notice_due(SLOT, D(2026, 10, 1, 20, 30, 50), 10))

    def test_a_timer_that_starts_in_the_future_is_never_due(self):
        # a timer may start "ahead" of the clock after a manual session
        self.assertFalse(actions.timer_notice_due(SLOT, SLOT + datetime.timedelta(minutes=30), 10))

    def test_every_minute_slot_counts_one_more_minute(self):
        start = D(2026, 10, 1, 20, 3, 41)
        slots = [D(2026, 10, 1, 20, 3) + datetime.timedelta(minutes=i) for i in range(0, 61)]
        self.assertEqual([s.minute for s in slots if actions.timer_notice_due(s, start, 10)], [13, 23, 33, 43, 53, 3])


class RefreshTimerNoticesTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        self.db.add(models.Game(id="g", name="Hollow Knight"))
        self.db.commit()

    def refresh(self, ready=True):
        with mock.patch.object(actions.push, "is_ready", return_value=ready), mock.patch.object(actions.push, "notify_timer", new=mock.AsyncMock()) as notify:
            result = asyncio.run(actions.refresh_timer_notices(self.db, SLOT))
        return result, notify

    def test_only_the_timers_that_are_due_are_refreshed(self):
        due = add_running(self.db, 1, started(30))
        add_running(self.db, 2, started(25))
        result, notify = self.refresh()
        self.assertEqual(result, "1 timers")
        notify.assert_awaited_once_with(1, "Hollow Knight", due.start_time)

    def test_each_timer_follows_the_interval_of_its_user(self):
        add_running(self.db, 1, started(30))  # default: 10 minutes
        add_running(self.db, 2, started(30))  # asked for 20: 30 is not a multiple
        add_running(self.db, 3, started(30))  # asked for 15
        self.db.add_all([models.UserSettings(user_id=2, timer_notice_minutes=20), models.UserSettings(user_id=3, timer_notice_minutes=15)])
        self.db.commit()
        result, notify = self.refresh()
        self.assertEqual(sorted(call.args[0] for call in notify.await_args_list), [1, 3])
        self.assertEqual(result, "2 timers")

    def test_a_user_with_a_longer_interval_is_refreshed_on_theirs(self):
        add_running(self.db, 2, started(40))
        self.db.add(models.UserSettings(user_id=2, timer_notice_minutes=20))
        self.db.commit()
        _, notify = self.refresh()
        notify.assert_awaited_once()

    def test_finished_timers_are_ignored(self):
        add_running(self.db, 1, started(30), active=False)
        _, notify = self.refresh()
        notify.assert_not_awaited()

    def test_nothing_happens_while_push_is_not_ready(self):
        add_running(self.db, 1, started(30))
        result, notify = self.refresh(ready=False)
        self.assertEqual(result, "")
        notify.assert_not_awaited()

    def test_the_default_is_never_below_the_minimum(self):
        self.assertGreaterEqual(user_settings.DEFAULT_TIMER_NOTICE_MINUTES, user_settings.MIN_TIMER_NOTICE_MINUTES)


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
