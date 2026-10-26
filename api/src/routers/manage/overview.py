"""The panel's home: counts and what may need the admin's attention."""
import datetime

from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...auth import get_db
from ...database import models
from .common import router


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    return {
        "users": db.query(func.count(models.User.id)).scalar(),
        "games": db.query(func.count(models.Game.id)).scalar(),
        "timers": db.query(func.count(models.GameTimer.id)).scalar(),
        "active_timers": db.query(func.count(models.GameTimer.id))
        .filter(models.GameTimer.is_active == True)  # noqa: E712
        .scalar(),
        "library": db.query(func.count(models.UserGame.id)).scalar(),
    }


# A timer left running this long is almost surely forgotten (the hourly job only nudges its owner).
STALE_TIMER_HOURS = 12


@router.get("/attention")
def attention(db: Session = Depends(get_db)):
    """What the admin may want to look at: forgotten timers, players the bot cannot reach, games without RAWG
    metadata and the challenges players have proposed that nobody has answered. Computed on request, like every
    other figure."""
    cutoff = datetime.datetime.now() - datetime.timedelta(hours=STALE_TIMER_HOURS)
    stale = (
        db.query(models.GameTimer)
        .filter(models.GameTimer.is_active == True, models.GameTimer.start_time < cutoff)  # noqa: E712
    )
    oldest = (
        stale.join(models.User, models.User.id == models.GameTimer.user_id)
        .join(models.Game, models.Game.id == models.GameTimer.game_id)
        .with_entities(models.User.username, models.Game.name, models.GameTimer.start_time)
        .order_by(models.GameTimer.start_time)
        .limit(5)
        .all()
    )
    return {
        "stale_timer_hours": STALE_TIMER_HOURS,
        "stale_timers": stale.count(),
        "stale_timers_oldest": [{"user": u, "game": g, "start_time": s.isoformat()} for u, g, s in oldest],
        "users_without_telegram": db.query(func.count(models.User.id))
        .filter(models.User.is_active == 1, models.User.telegram_id.is_(None), models.not_god())
        .scalar(),
        "games_without_rawg": db.query(func.count(models.Game.id)).filter(models.Game.rawg_id.is_(None)).scalar(),
        "pending_challenge_proposals": db.query(func.count(models.ChallengeProposal.id)).filter(models.ChallengeProposal.status == "pending").scalar(),
    }
