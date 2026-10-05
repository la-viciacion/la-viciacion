"""In-process scheduler: the time-driven work that used to depend on an
external cron calling the API every minute.

Achievements and ranking announcements are event-driven (they run when a timer
stops or an admin edits data); totals, rankings and streaks are computed from the
sessions when asked for, so nothing has to be reset when the season changes. Only
what nothing else can trigger remains here:

  weekly_summary    once a week at the configured day/time (admin panel)
  timer_notices     every minute, refreshes the pinned push notification of the running
                    timers that are due (each user chooses the interval, 10 minutes or more).
                    Switched off by TIMER_NOTICE_REFRESH: only the first notification is sent
  forgotten_timers  every hour, reminds who has a timer running for too long
  daily_streaks     every day at 05:00, checks achievements + announces lost streaks
  daily_wishlist    every day at 09:00, refreshes the release date of the games somebody waits for
                    and, while actions.WISHLIST_PRIVATE_NOTICE is on (off), tells who wished a game that comes out today
  wishlist_eve      every day at 12:30, tells the group which wished games come out tomorrow

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
from . import actions, push, seasons, settings
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

TICK_SECONDS = 30
STARTUP_DELAY_SECONDS = 5

WEEKLY_GRACE = datetime.timedelta(hours=6)
HOURLY_GRACE = datetime.timedelta(minutes=10)
DAILY_GRACE = datetime.timedelta(hours=3)
DAILY_STREAKS_HOUR = 5
DAILY_WISHLIST_HOUR = 9
# After the 09:00 refresh, so a date that slipped overnight is already corrected when the group is told
WISHLIST_EVE_TIME = (12, 30)
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


def _run(db: Session, job: str, coroutine_factory, use_lock: bool = False) -> None:
    logger.info(f"Scheduled job {job} starting")
    try:
        if use_lock:
            with actions._check_lock:
                status = asyncio.run(coroutine_factory())
        else:
            status = asyncio.run(coroutine_factory())
        _finish(db, job, f"ok: {status}" if status else "ok")
    except Exception as e:
        logger.error(f"Scheduled job {job} failed: {e}")
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


async def _timer_notices(db: Session, slot: datetime.datetime) -> str:
    return await actions.refresh_timer_notices(db, slot)


async def _forgotten_timers(db: Session) -> str:
    for user in users.get_users(db):
        await actions.check_forgotten_timer(db, user)
    return ""


async def _daily_streaks(db: Session) -> str:
    await actions.check_users(db, silent=False, announce_streak_loss=True)
    return ""


async def _daily_wishlist(db: Session) -> str:
    return await actions.check_wishlist(db, datetime.date.today())


async def _wishlist_eve(db: Session) -> str:
    return await actions.announce_wishlist_eve(db, datetime.date.today() + datetime.timedelta(days=1))


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

        if TIMER_NOTICE_REFRESH and notifications and push.is_ready():
            slot = minute_slot(now)
            if is_due(now, slot, _last_run(db, "timer_notices"), TIMER_NOTICE_GRACE) and _claim(db, "timer_notices", slot, now):
                _run(db, "timer_notices", lambda: _timer_notices(db, slot))

        if notifications:
            slot = hourly_slot(now)
            if is_due(now, slot, _last_run(db, "forgotten_timers"), HOURLY_GRACE) and _claim(db, "forgotten_timers", slot, now):
                _run(db, "forgotten_timers", lambda: _forgotten_timers(db))

        slot = daily_slot(now, DAILY_STREAKS_HOUR)
        if is_due(now, slot, _last_run(db, "daily_streaks"), DAILY_GRACE) and _claim(db, "daily_streaks", slot, now):
            _run(db, "daily_streaks", lambda: _daily_streaks(db), use_lock=True)

        slot = daily_slot(now, DAILY_WISHLIST_HOUR)
        if is_due(now, slot, _last_run(db, "daily_wishlist"), DAILY_GRACE) and _claim(db, "daily_wishlist", slot, now):
            _run(db, "daily_wishlist", lambda: _daily_wishlist(db))

        if notifications:
            slot = daily_slot(now, *WISHLIST_EVE_TIME)
            if is_due(now, slot, _last_run(db, "wishlist_eve"), DAILY_GRACE) and _claim(db, "wishlist_eve", slot, now):
                _run(db, "wishlist_eve", lambda: _wishlist_eve(db))


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
                logger.error(f"Scheduler tick failed: {e}")
            stop.wait(TICK_SECONDS)

    _thread = threading.Thread(target=loop, name="scheduler", daemon=True)
    _thread.start()
    logger.info("Scheduler started")
