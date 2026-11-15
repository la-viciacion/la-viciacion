"""Early access: which games are in it. Only the day a game entered it is stored (`games.early_access_date`); being in it is
derived from that day and the official launch (`games.release_date`), so it ends by itself the day the launch is reached."""
import datetime

from sqlalchemy.orm import Session

from ..database import models


def is_early_access(early_access_date: datetime.date | None, release_date: datetime.date | None, today: datetime.date) -> bool:
    """In early access: it has entered it and its official launch is not yet reached (an undated launch is not reached)."""
    return early_access_date is not None and early_access_date <= today and (release_date is None or release_date > today)


def to_refresh(db: Session, today: datetime.date) -> list[models.Game]:
    """The games that are in early access, or will be, and IGDB knows: their launch day is what ends it, and it slips. The
    soonest first (the refresh is capped, so the launch that is about to come is checked before one far away)."""
    return (
        db.query(models.Game)
        .filter(
            models.Game.igdb_id.isnot(None),
            models.Game.early_access_date.isnot(None),
            models.Game.release_date.is_(None) | (models.Game.release_date >= today),
        )
        .order_by(models.Game.release_date.is_(None), models.Game.release_date, models.Game.id)
        .all()
    )
