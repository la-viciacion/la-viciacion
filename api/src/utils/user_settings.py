"""Personal preferences of each user (table `user_settings`).

A NULL column, or no row at all, means "use the default", so the defaults live
here and can change without touching anyone's data. Global, admin-edited values
are a different thing: see settings.py (`app_settings`).
"""
import datetime

from sqlalchemy.orm import Session

from ..database import models

DEFAULT_FORGOTTEN_TIMER_HOURS = 4
MIN_FORGOTTEN_TIMER_HOURS = 1
MAX_FORGOTTEN_TIMER_HOURS = 24
# Push services throttle senders that refresh too often: never below 10 (the database CHECK says the same)
DEFAULT_TIMER_NOTICE_MINUTES = 10
MIN_TIMER_NOTICE_MINUTES = 10
MAX_TIMER_NOTICE_MINUTES = 120
DEFAULT_SHOW_PLAYING = True
DEFAULT_FORGOTTEN_TIMER_CHANNEL = True
PLACE_COLUMNS = ("place_name", "place_latitude", "place_longitude")
EARLIEST_BIRTH_DATE = datetime.date(1900, 1, 1)


def valid_forgotten_timer_hours(hours) -> bool:
    # bool is an int subclass: `true` must not pass as 1 hour
    return isinstance(hours, int) and not isinstance(hours, bool) and MIN_FORGOTTEN_TIMER_HOURS <= hours <= MAX_FORGOTTEN_TIMER_HOURS


def valid_timer_notice_minutes(minutes) -> bool:
    return isinstance(minutes, int) and not isinstance(minutes, bool) and MIN_TIMER_NOTICE_MINUTES <= minutes <= MAX_TIMER_NOTICE_MINUTES


def valid_place(changes: dict) -> bool:
    """A place is its name and both coordinates, or nothing at all: the three are set together or cleared together."""
    given = [changes.get(column) for column in PLACE_COLUMNS if column in changes]
    if not given:
        return True
    return len(given) == len(PLACE_COLUMNS) and (all(value is None for value in given) or all(value is not None for value in given))


def valid_birth_date(day, today: datetime.date | None = None) -> bool:
    return day is None or EARLIEST_BIRTH_DATE <= day <= (today or datetime.date.today())


def place(db: Session, user_id: int) -> tuple[float, float] | None:
    """(latitude, longitude) of the city the user chose, or None if they have not."""
    row = db.get(models.UserSettings, user_id)
    if row is None or row.place_latitude is None or row.place_longitude is None:
        return None
    return float(row.place_latitude), float(row.place_longitude)


def birth_date(db: Session, user_id: int) -> datetime.date | None:
    row = db.get(models.UserSettings, user_id)
    return None if row is None else row.birth_date


def forgotten_timer_hours(db: Session, user_id: int) -> int:
    """Hours a timer of this user may run before the reminder (their own or the default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None or row.forgotten_timer_hours is None:
        return DEFAULT_FORGOTTEN_TIMER_HOURS
    return row.forgotten_timer_hours


def forgotten_timer_channels(db: Session, user_id: int) -> tuple[bool, bool]:
    """(telegram, push): where this user wants the forgotten-timer notice. Both off means no notice."""
    row = db.get(models.UserSettings, user_id)
    telegram = row.forgotten_timer_telegram if row else None
    push = row.forgotten_timer_push if row else None
    return (
        DEFAULT_FORGOTTEN_TIMER_CHANNEL if telegram is None else bool(telegram),
        DEFAULT_FORGOTTEN_TIMER_CHANNEL if push is None else bool(push),
    )


def timer_notice_minutes(db: Session, user_id: int) -> int:
    """Minutes between refreshes of this user's running-timer notification (their own or the default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None or row.timer_notice_minutes is None:
        return DEFAULT_TIMER_NOTICE_MINUTES
    return row.timer_notice_minutes


def show_playing(db: Session, user_id: int) -> bool:
    """Whether the others see this user in "playing now" (their own choice or the default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None or row.show_playing is None:
        return DEFAULT_SHOW_PLAYING
    return bool(row.show_playing)


def get(db: Session, user_id: int) -> dict:
    """What the profile form shows: the user's own value (None = default) and the default."""
    row = db.get(models.UserSettings, user_id)
    return {
        "forgotten_timer_hours": row.forgotten_timer_hours if row else None,
        "timer_notice_minutes": row.timer_notice_minutes if row else None,
        "show_playing": None if row is None or row.show_playing is None else bool(row.show_playing),
        "forgotten_timer_telegram": None if row is None or row.forgotten_timer_telegram is None else bool(row.forgotten_timer_telegram),
        "forgotten_timer_push": None if row is None or row.forgotten_timer_push is None else bool(row.forgotten_timer_push),
        "place_name": row.place_name if row else None,
        "place_latitude": None if row is None or row.place_latitude is None else float(row.place_latitude),
        "place_longitude": None if row is None or row.place_longitude is None else float(row.place_longitude),
        "birth_date": row.birth_date.isoformat() if row is not None and row.birth_date is not None else None,
        "defaults": {
            "forgotten_timer_telegram": DEFAULT_FORGOTTEN_TIMER_CHANNEL,
            "forgotten_timer_push": DEFAULT_FORGOTTEN_TIMER_CHANNEL,
            "forgotten_timer_hours": DEFAULT_FORGOTTEN_TIMER_HOURS,
            "timer_notice_minutes": DEFAULT_TIMER_NOTICE_MINUTES,
            "show_playing": DEFAULT_SHOW_PLAYING,
        },
    }


def update(db: Session, user_id: int, changes: dict) -> dict:
    """Apply the settings present in `changes` (None resets one to its default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None:
        row = models.UserSettings(user_id=user_id)
        db.add(row)
    if "forgotten_timer_hours" in changes:
        row.forgotten_timer_hours = changes["forgotten_timer_hours"]
    if "timer_notice_minutes" in changes:
        row.timer_notice_minutes = changes["timer_notice_minutes"]
    if "show_playing" in changes:
        row.show_playing = changes["show_playing"]
    for column in ("forgotten_timer_telegram", "forgotten_timer_push", *PLACE_COLUMNS, "birth_date"):
        if column in changes:
            setattr(row, column, changes[column])
    db.commit()
    return get(db, user_id)
