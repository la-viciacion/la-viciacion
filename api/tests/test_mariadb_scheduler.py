"""The in-process scheduler (MariaDB required, see api_support.py): which job runs at a given moment, that a
restart never repeats a run, what it records in `job_runs`, and that a failing job does not stop the rest.
`tick(now)` takes the clock as an argument, so every case names the moment it is about. The jobs' own work
(summaries, reminders, achievement checks) is replaced by recorders; it is tested in
test_mariadb_background_notices.py and test_mariadb_background_work.py."""
import datetime
from datetime import timedelta
from unittest import mock

from sqlalchemy import text

from src.database import database
from src.utils import actions, push, scheduler
from tests.api_support import ApiTestCase

MONDAY = datetime.datetime(2026, 3, 2)  # a Monday: the default weekly summary is Monday 09:00


def at(hour, minute=0, second=0, day=0) -> datetime.datetime:
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


class SchedulerTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []

        async def weekly_resume(db, user, weeks_ago=0, silent=False):
            self.calls.append(("weekly_resume", user.username, weeks_ago, silent))

        async def check_forgotten_timer(db, user):
            self.calls.append(("forgotten", user.username))

        async def announce_lost_streaks(db, today=None, silent=False):
            self.calls.append(("daily_streaks", silent))

        for patcher in (
            mock.patch.object(actions, "weekly_resume", new=weekly_resume),
            mock.patch.object(actions, "check_forgotten_timer", new=check_forgotten_timer),
            mock.patch.object(actions, "announce_lost_streaks", new=announce_lost_streaks),
            mock.patch.object(actions, "push_has_devices", return_value=False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.ana = self.user("ana", telegram_id=111)

    def jobs(self) -> dict:
        return {job: (when, status) for job, when, status in self.rows("SELECT job, last_run_at, last_status FROM job_runs")}

    def names(self):
        return [call[0] for call in self.calls]


class DueTimeTests(ApiTestCase):
    """The pure functions that decide when something is due."""

    def test_the_weekly_slot_is_the_latest_occurrence_not_after_now(self):
        self.assertEqual(scheduler.weekly_slot(at(9, 30), 0, "09:00"), at(9))
        self.assertEqual(scheduler.weekly_slot(at(8, 59), 0, "09:00"), at(9, day=-7))  # not yet this week
        self.assertEqual(scheduler.weekly_slot(at(9, day=3), 0, "09:00"), at(9))  # Thursday: Monday's slot
        self.assertEqual(scheduler.weekly_slot(at(9, day=3), 3, "18:30"), at(18, 30, day=-4))

    def test_the_daily_and_hourly_slots(self):
        self.assertEqual(scheduler.daily_slot(at(6), 5), at(5))
        self.assertEqual(scheduler.daily_slot(at(4, 59), 5), at(5, day=-1))
        self.assertEqual(scheduler.hourly_slot(at(10, 42, 17)), at(10))
        self.assertEqual(scheduler.minute_slot(at(10, 42, 17)), at(10, 42))

    def test_something_is_due_inside_its_grace_window_when_it_has_not_run_since_the_slot(self):
        grace = timedelta(hours=1)
        self.assertTrue(scheduler.is_due(at(9, 30), at(9), None, grace))
        self.assertTrue(scheduler.is_due(at(9, 30), at(9), at(8), grace))  # last run was before the slot
        self.assertFalse(scheduler.is_due(at(9, 30), at(9), at(9, 5), grace))  # already ran for this slot
        self.assertFalse(scheduler.is_due(at(10, 1), at(9), None, grace))  # too late: not sent on Thursday
        self.assertTrue(scheduler.is_due(at(10), at(9), None, grace))  # the edge of the window


class JobBookkeepingTests(SchedulerTestCase):
    def claim(self, slot, now):
        with database.SessionLocal() as db:
            return scheduler._claim(db, "weekly_summary", slot, now)

    def test_a_slot_is_claimed_by_one_run_only(self):
        self.assertTrue(self.claim(at(9), at(9, 1)))
        self.assertFalse(self.claim(at(9), at(9, 2)))  # the same slot again, e.g. another process
        self.assertTrue(self.claim(at(9, day=7), at(9, 1, day=7)))  # the next week's slot is a new one

    def test_the_status_is_recorded(self):
        scheduler.tick(at(9, 1))
        when, status = self.jobs()["weekly_summary"]
        self.assertEqual((when, status), (at(9, 1), "ok: 1 users"))


class WeeklySummaryJobTests(SchedulerTestCase):
    def test_it_runs_for_the_users_that_can_be_reached_at_the_configured_moment(self):
        self.user("loner")  # no Telegram, no push device
        scheduler.tick(at(9, 1))
        self.assertEqual([c for c in self.calls if c[0] == "weekly_resume"], [("weekly_resume", "ana", 1, False)])

    def test_a_user_with_only_push_devices_is_included(self):
        self.user("pushy")
        with mock.patch.object(actions, "push_has_devices", side_effect=lambda user_id: user_id != self.ana):
            scheduler.tick(at(9, 1))
        self.assertEqual({c[1] for c in self.calls if c[0] == "weekly_resume"}, {"ana", "pushy"})

    def test_it_does_not_repeat_inside_the_same_slot_even_after_a_restart(self):
        scheduler.tick(at(9, 1))
        scheduler.tick(at(9, 1, 30))
        scheduler.tick(at(11))
        self.assertEqual(self.names().count("weekly_resume"), 1)

    def test_a_run_missed_while_the_server_was_down_still_happens_inside_the_grace_window(self):
        scheduler.tick(at(14, 59))  # 5 h 59 min late
        self.assertEqual(self.names().count("weekly_resume"), 1)

    def test_a_run_missed_by_more_than_the_grace_is_not_sent_late(self):
        scheduler.tick(at(15, 1))
        scheduler.tick(at(9, day=3))
        self.assertEqual(self.names().count("weekly_resume"), 0)

    def test_it_runs_again_the_following_week(self):
        scheduler.tick(at(9, 1))
        scheduler.tick(at(9, 1, day=7))
        self.assertEqual(self.names().count("weekly_resume"), 2)

    def test_the_day_and_time_are_the_admin_s_choice(self):
        self.set_settings(**{"weekly.weekday": 2, "weekly.time": "18:30"})
        scheduler.tick(at(9, 1))  # Monday 09:01: not the moment any more
        self.assertEqual(self.names().count("weekly_resume"), 0)
        scheduler.tick(at(18, 31, day=2))  # Wednesday 18:31
        self.assertEqual(self.names().count("weekly_resume"), 1)

    def test_the_switches_stop_it(self):
        self.set_settings(**{"weekly.enabled": False})
        scheduler.tick(at(9, 1))
        self.assertEqual(self.names().count("weekly_resume"), 0)
        self.set_settings(**{"weekly.enabled": True, "notifications.enabled": False})
        scheduler.tick(at(9, 2))
        self.assertEqual(self.names().count("weekly_resume"), 0)


class HourlyAndDailyJobTests(SchedulerTestCase):
    def test_forgotten_timers_are_checked_once_an_hour_for_every_user(self):
        self.user("bea")
        scheduler.tick(at(10, 5))
        scheduler.tick(at(10, 6))
        self.assertEqual(sorted(c[1] for c in self.calls if c[0] == "forgotten"), ["ana", "bea"])
        self.calls.clear()
        scheduler.tick(at(11, 0, 20))
        self.assertEqual(len([c for c in self.calls if c[0] == "forgotten"]), 2)

    def test_the_hourly_check_has_a_short_grace(self):
        scheduler.tick(at(10, 11))
        self.assertEqual([c for c in self.calls if c[0] == "forgotten"], [])

    def test_the_hourly_check_follows_the_notifications_switch(self):
        self.set_settings(**{"notifications.enabled": False})
        scheduler.tick(at(10, 5))
        self.assertEqual([c for c in self.calls if c[0] == "forgotten"], [])

    def test_the_daily_check_announces_lost_streaks_and_runs_at_five(self):
        scheduler.tick(at(5, 10))
        self.assertIn(("daily_streaks", False), self.calls)
        self.calls.clear()
        scheduler.tick(at(5, 40))
        scheduler.tick(at(8, 30))
        self.assertEqual([c for c in self.calls if c[0] == "daily_streaks"], [])

    def test_the_daily_check_waits_for_five_and_is_not_made_up_for_much_later(self):
        scheduler.tick(at(4, 59))
        scheduler.tick(at(8, 30))  # more than the 3 hours of grace after 05:00
        self.assertEqual([c for c in self.calls if c[0] == "daily_streaks"], [])

    def test_the_daily_check_does_not_depend_on_the_notifications_switch(self):
        self.set_settings(**{"notifications.enabled": False})
        scheduler.tick(at(5, 10))
        self.assertEqual([c for c in self.calls if c[0] == "daily_streaks"], [("daily_streaks", False)])


class TimerNoticeJobTests(SchedulerTestCase):
    def test_the_refresh_is_off_by_default_and_never_runs(self):
        self.assertFalse(scheduler.TIMER_NOTICE_REFRESH)
        with mock.patch.object(push, "is_ready", return_value=True):
            scheduler.tick(at(10, 5))
        self.assertNotIn("timer_notices", self.jobs())

    def test_when_switched_on_it_runs_every_minute_once(self):
        refreshed = []

        async def refresh(db, slot):
            refreshed.append(slot)
            return "2 timers"

        with mock.patch.object(scheduler, "TIMER_NOTICE_REFRESH", True), mock.patch.object(push, "is_ready", return_value=True), \
             mock.patch.object(actions, "refresh_timer_notices", new=refresh):
            scheduler.tick(at(10, 5, 10))
            scheduler.tick(at(10, 5, 40))  # the same minute
            scheduler.tick(at(10, 6, 5))
        self.assertEqual(refreshed, [at(10, 5), at(10, 6)])
        self.assertEqual(self.jobs()["timer_notices"][1], "ok: 2 timers")

    def test_without_push_ready_it_does_not_run_even_when_switched_on(self):
        with mock.patch.object(scheduler, "TIMER_NOTICE_REFRESH", True), mock.patch.object(push, "is_ready", return_value=False):
            scheduler.tick(at(10, 5))
        self.assertNotIn("timer_notices", self.jobs())


class FailingJobTests(SchedulerTestCase):
    def test_a_failing_job_is_recorded_and_the_others_still_run(self):
        async def broken(db, today=None, silent=False):
            raise RuntimeError("streaks exploded")

        with mock.patch.object(actions, "announce_lost_streaks", new=broken):
            scheduler.tick(at(5, 10))
        self.assertEqual(self.jobs()["daily_streaks"][1], "error: streaks exploded")
        scheduler.tick(at(9, 1, day=7))  # next week: other jobs are unaffected
        self.assertEqual(self.jobs()["weekly_summary"][1], "ok: 1 users")

    def test_a_failure_does_not_make_the_job_repeat_in_the_same_slot(self):
        async def broken(db, today=None, silent=False):
            raise RuntimeError("nope")

        with mock.patch.object(actions, "announce_lost_streaks", new=broken):
            scheduler.tick(at(5, 10))
            scheduler.tick(at(5, 12))
        self.assertEqual(self.jobs()["daily_streaks"][1], "error: nope")
        self.calls.clear()
        scheduler.tick(at(5, 14))
        self.assertEqual([c for c in self.calls if c[0] == "daily_streaks"], [])  # still the same slot

    def test_a_long_error_message_fits_the_column(self):
        async def broken(db, today=None, silent=False):
            raise RuntimeError("x" * 600)

        with mock.patch.object(actions, "announce_lost_streaks", new=broken):
            scheduler.tick(at(5, 10))
        self.assertEqual(len(self.jobs()["daily_streaks"][1]), 255)


class LoopTests(SchedulerTestCase):
    def test_the_thread_keeps_going_when_a_tick_fails_and_starts_only_once(self):
        ticks = []

        class OneShotEvent:
            def __init__(self):
                self.waits = 0

            def wait(self, seconds):
                self.waits += 1

            def is_set(self):
                return len(ticks) >= 3

        started = []

        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target

            def start(self):
                started.append(self)
                self.target()

            def is_alive(self):
                return True

        def tick():
            ticks.append(1)
            if len(ticks) == 1:
                raise RuntimeError("first tick fails")

        with mock.patch.object(scheduler, "_thread", None), mock.patch.object(scheduler.threading, "Thread", FakeThread), \
             mock.patch.object(scheduler.threading, "Event", OneShotEvent), mock.patch.object(scheduler, "tick", new=tick):
            scheduler.start()
            self.assertEqual(len(ticks), 3)  # it went on after the failure
            scheduler.start()  # a second call finds the thread alive
            self.assertEqual(len(started), 1)
