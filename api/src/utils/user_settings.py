"""Personal preferences of each user (table `user_settings`).

A NULL column, or no row at all, means "use the default", so the defaults live
here and can change without touching anyone's data. Global, admin-edited values
are a different thing: see settings.py (`app_settings`).
"""
from sqlalchemy.orm import Session

from ..database import models

DEFAULT_FORGOTTEN_TIMER_HOURS = 4
MIN_FORGOTTEN_TIMER_HOURS = 1
MAX_FORGOTTEN_TIMER_HOURS = 24


def valid_forgotten_timer_hours(hours) -> bool:
    # bool is an int subclass: `true` must not pass as 1 hour
    return isinstance(hours, int) and not isinstance(hours, bool) and MIN_FORGOTTEN_TIMER_HOURS <= hours <= MAX_FORGOTTEN_TIMER_HOURS


def forgotten_timer_hours(db: Session, user_id: int) -> int:
    """Hours a timer of this user may run before the reminder (their own or the default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None or row.forgotten_timer_hours is None:
        return DEFAULT_FORGOTTEN_TIMER_HOURS
    return row.forgotten_timer_hours


def get(db: Session, user_id: int) -> dict:
    """What the profile form shows: the user's own value (None = default) and the default."""
    row = db.get(models.UserSettings, user_id)
    return {
        "forgotten_timer_hours": row.forgotten_timer_hours if row else None,
        "defaults": {"forgotten_timer_hours": DEFAULT_FORGOTTEN_TIMER_HOURS},
    }


def update(db: Session, user_id: int, changes: dict) -> dict:
    """Apply the settings present in `changes` (None resets one to its default)."""
    row = db.get(models.UserSettings, user_id)
    if row is None:
        row = models.UserSettings(user_id=user_id)
        db.add(row)
    if "forgotten_timer_hours" in changes:
        row.forgotten_timer_hours = changes["forgotten_timer_hours"]
    db.commit()
    return get(db, user_id)
