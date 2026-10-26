"""In-process scheduler: the time-driven work that used to depend on an
external cron calling the API every minute.

Achievements and ranking announcements are event-driven (they run when a timer
stops or an admin edits data); totals, rankings and streaks are computed from the
sessions when asked for, so nothing has to be reset when the season changes. Only
what nothing else can trigger remains here:

  weekly_summary    once a week at the configured day/time (admin panel)
  monthly_recap     once a month at the configured day/time (admin panel): the recap of the month that ended
  annual_recap      once a year, in December (20-28) or January (1-5) as configured: the recap of the season
  timer_notices     every minute, refreshes the pinned push notification of the running
                    timers that are due (each user chooses the interval, 10 minutes or more).
                    Switched off by TIMER_NOTICE_REFRESH: only the first notification is sent
  forgotten_timers  every hour, reminds who has a timer running for too long
  daily_streaks     every day at 05:00, announces the streaks lost the day before
  daily_wishlist    every day at 09:00, refreshes the release date of the games somebody waits for
                    and, while actions.WISHLIST_PRIVATE_NOTICE is on (off), tells who wished a game that comes out today
  wishlist_eve      every day at `wishlist.time` (12:30), tells the group which wished games come out tomorrow
  wishlist_week     every Sunday at `wishlist.time`, tells the group which wished games come out in the next 7 days.
                    Only one of wishlist_eve and wishlist_week runs: `wishlist.group_notice`
  inbox_purge       every day at 04:00, deletes the inbox notices older than `inbox.retention_days`

Every run is recorded in `job_runs`, so a restart never repeats a run and a job
that was due while the API was down still runs when it comes back, within a
grace window (a summary is not sent on Thursday because the server was off on
Monday). The due-time logic is in pure functions to be testable without clocks.
"""
import asyncio
import datetime
import threading

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..crud import users
from ..database import models
from ..database.database import SessionLocal
from . import actions, inbox, push, recap_notices, settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

TICK_SECONDS = 30
STARTUP_DELAY_SECONDS = 5

WEEKLY_GRACE = datetime.timedelta(hours=6)
MONTHLY_GRACE = datetime.timedelta(hours=12)
ANNUAL_GRACE = datetime.timedelta(hours=12)
HOURLY_GRACE = datetime.timedelta(minutes=10)
DAILY_GRACE = datetime.timedelta(hours=3)
DAILY_STREAKS_HOUR = 5
INBOX_PURGE_HOUR = 4
DAILY_WISHLIST_HOUR = 9
# The week the weekly wishlist notice tells about starts the day after (Monday to Sunday)
WISHLIST_WEEKLY_WEEKDAY = 6
# Off: the notification is shown once, when the timer starts. The job, the per-user interval
# (user_settings.timer_notice_minutes) and its column stay, so turning this on brings the refresh back.
TIMER_NOTICE_REFRESH = False
TIMER_NOTICE_GRACE = datetime.timedelta(minutes=2)  # a late refresh is useless: the next one is due soon


# ── when is something due (pure) ────────────────────────────
def weekly_slot(now: datetime.datetime, weekday: int, hhmm: str) -> datetime.datetime:
    """Latest occurrence (<= now) of `weekday` (0 = Monday) at HH:MM."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    days_back = (now.weekday() - weekday) % 7
    slot = (now - datetime.timedelta(days=days_back)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if slot > now:
        slot -= datetime.timedelta(days=7)
    return slot


def monthly_slot(now: datetime.datetime, day: int, hhmm: str) -> datetime.datetime:
    """Latest occurrence (<= now) of `day` of the month (1-28, so every month has it) at HH:MM."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    slot = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
    if slot > now:
        slot = (slot.replace(day=1) - datetime.timedelta(days=1)).replace(day=day)
    return slot


def annual_slot(now: datetime.datetime, month: int, day: int, hhmm: str) -> datetime.datetime:
    """Latest occurrence (<= now) of `day` of `month` at HH:MM (the day is up to 28, so every year has it)."""
    hour, minute = (int(part) for part in hhmm.split(":"))
    slot = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
    return slot if slot <= now else slot.replace(year=slot.year - 1)


def daily_slot(now: datetime.datetime, hour: int, minute: int = 0) -> datetime.datetime:
    slot = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return slot - datetime.timedelta(days=1) if slot > now else slot


def hourly_slot(now: datetime.datetime) -> datetime.datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def minute_slot(now: datetime.datetime) -> datetime.datetime:
    return now.replace(second=0, microsecond=0)


def is_due(now: datetime.datetime, slot: datetime.datetime, last_run: datetime.datetime | None, grace: datetime.timedelta) -> bool:
    """Due when the slot has passed, is still inside the grace window and has not run since."""
    return (now - slot) <= grace and (last_run is None or last_run < slot)


# ── job bookkeeping ─────────────────────────────────────────
def _last_run(db: Session, job: str) -> datetime.datetime | None:
    row = db.get(models.JobRun, job)
    return row.last_run_at if row else None


def _claim(db: Session, job: str, slot: datetime.datetime, now: datetime.datetime) -> bool:
    """Atomically mark the job as run for this slot; False if somebody else already did."""
    if db.get(models.JobRun, job) is None:
        try:
            db.add(models.JobRun(job=job, last_run_at=now, last_status="running"))
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            return False
    result = db.execute(
        update(models.JobRun)
        .where(models.JobRun.job == job, models.JobRun.last_run_at < slot)
        .values(last_run_at=now, last_status="running")
    )
    db.commit()
    return result.rowcount == 1


def _finish(db: Session, job: str, status: str) -> None:
    db.execute(update(models.JobRun).where(models.JobRun.job == job).values(last_status=status[:255]))
    db.commit()


def _run(db: Session, job: str, coroutine_factory) -> None:
    logger.info(f"Scheduled job {job} starting")
    try:
        status = asyncio.run(coroutine_factory())
        _finish(db, job, f"ok: {status}" if status else "ok")
    except Exception as e:
        logger.error(f"Scheduled job {job} failed: {e}", exc_info=True)
        _finish(db, job, f"error: {e}")


# ── the jobs ────────────────────────────────────────────────
async def _weekly_summary(db: Session) -> str:
    sent = 0
    for user in users.get_users(db):
        if user.telegram_id is None and not actions.push_has_devices(user.id):
            continue
        await actions.weekly_resume(db, user, weeks_ago=1, silent=False)
        sent += 1
    return f"{sent} users"


async def _monthly_recap(db: Session, slot: datetime.datetime) -> str:
    """The recap of the month before the slot's one (slot on 1 October: September)."""
    period = recap_notices.previous_month(slot.date())
    return f"{period.key}: " + recap_notices.describe(await recap_notices.announce_recap(db, period))


async def _annual_recap(db: Session, slot: datetime.datetime) -> str:
    """The recap of the season: the running one for a December slot, the one that ended for a January slot."""
    period = recap_notices.annual_period(slot.date())
    return f"{period.key}: " + recap_notices.describe(await recap_notices.announce_recap(db, period))


async def _timer_notices(db: Session, slot: datetime.datetime) -> str:
    return await actions.refresh_timer_notices(db, slot)


async def _forgotten_timers(db: Session) -> str:
    for user in users.get_users(db):
        await actions.check_forgotten_timer(db, user)
    return ""


async def _daily_streaks(db: Session) -> str:
    await actions.announce_lost_streaks(db)
    return ""


async def _daily_wishlist(db: Session) -> str:
    return await actions.check_wishlist(db, datetime.date.today())


async def _inbox_purge(db: Session) -> str:
    return f"{inbox.purge(db)} deleted"


async def _wishlist_eve(db: Session) -> str:
    return await actions.announce_wishlist_eve(db, datetime.date.today() + datetime.timedelta(days=1))


async def _wishlist_week(db: Session, slot: datetime.datetime) -> str:
    return await actions.announce_wishlist_week(db, slot.date())


# ── the loop ────────────────────────────────────────────────
def tick(now: datetime.datetime | None = None) -> None:
    """Run whatever is due. Called every TICK_SECONDS by the scheduler thread."""
    now = now or datetime.datetime.now()
    with SessionLocal() as db:
        notifications = settings.get("notifications.enabled")

        if notifications and settings.get("weekly.enabled"):
            slot = weekly_slot(now, settings.get("weekly.weekday"), settings.get("weekly.time"))
            if is_due(now, slot, _last_run(db, "weekly_summary"), WEEKLY_GRACE) and _claim(db, "weekly_summary", slot, now):
                _run(db, "weekly_summary", lambda: _weekly_summary(db))

        if notifications and settings.get("monthly.enabled"):
            slot = monthly_slot(now, settings.get("monthly.day"), settings.get("monthly.time"))
            if is_due(now, slot, _last_run(db, "monthly_recap"), MONTHLY_GRACE) and _claim(db, "monthly_recap", slot, now):
                _run(db, "monthly_recap", lambda: _monthly_recap(db, slot))

        if notifications and settings.get("annual.enabled"):
            slot = annual_slot(now, settings.get("annual.month"), settings.get("annual.day"), settings.get("annual.time"))
            if is_due(now, slot, _last_run(db, "annual_recap"), ANNUAL_GRACE) and _claim(db, "annual_recap", slot, now):
                _run(db, "annual_recap", lambda: _annual_recap(db, slot))

        if TIMER_NOTICE_REFRESH and notifications and push.is_ready():
            slot = minute_slot(now)
            if is_due(now, slot, _last_run(db, "timer_notices"), TIMER_NOTICE_GRACE) and _claim(db, "timer_notices", slot, now):
                _run(db, "timer_notices", lambda: _timer_notices(db, slot))

        if notifications:
            slot = hourly_slot(now)
            if is_due(now, slot, _last_run(db, "forgotten_timers"), HOURLY_GRACE) and _claim(db, "forgotten_timers", slot, now):
                _run(db, "forgotten_timers", lambda: _forgotten_timers(db))

        slot = daily_slot(now, INBOX_PURGE_HOUR)
        if is_due(now, slot, _last_run(db, "inbox_purge"), DAILY_GRACE) and _claim(db, "inbox_purge", slot, now):
            _run(db, "inbox_purge", lambda: _inbox_purge(db))

        slot = daily_slot(now, DAILY_STREAKS_HOUR)
        if is_due(now, slot, _last_run(db, "daily_streaks"), DAILY_GRACE) and _claim(db, "daily_streaks", slot, now):
            _run(db, "daily_streaks", lambda: _daily_streaks(db))

        slot = daily_slot(now, DAILY_WISHLIST_HOUR)
        if is_due(now, slot, _last_run(db, "daily_wishlist"), DAILY_GRACE) and _claim(db, "daily_wishlist", slot, now):
            _run(db, "daily_wishlist", lambda: _daily_wishlist(db))

        # One mode at a time (wishlist.group_notice): the day before, or once a week, never both
        wishlist_notice = settings.get("wishlist.group_notice")
        if notifications and wishlist_notice == "eve":
            slot = daily_slot(now, *(int(part) for part in settings.get("wishlist.time").split(":")))
            if is_due(now, slot, _last_run(db, "wishlist_eve"), DAILY_GRACE) and _claim(db, "wishlist_eve", slot, now):
                _run(db, "wishlist_eve", lambda: _wishlist_eve(db))

        if notifications and wishlist_notice == "weekly":
            slot = weekly_slot(now, WISHLIST_WEEKLY_WEEKDAY, settings.get("wishlist.time"))
            if is_due(now, slot, _last_run(db, "wishlist_week"), WEEKLY_GRACE) and _claim(db, "wishlist_week", slot, now):
                _run(db, "wishlist_week", lambda: _wishlist_week(db, slot))


_thread: threading.Thread | None = None


def start() -> None:
    """Start the scheduler thread (once per process)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    stop = threading.Event()

    def loop() -> None:
        stop.wait(STARTUP_DELAY_SECONDS)
        while not stop.is_set():
            try:
                tick()
            except Exception as e:
                logger.error(f"Scheduler tick failed: {e}", exc_info=True)
            stop.wait(TICK_SECONDS)

    _thread = threading.Thread(target=loop, name="scheduler", daemon=True)
    _thread.start()
    logger.info("Scheduler started")
