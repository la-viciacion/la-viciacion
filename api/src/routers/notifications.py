"""The caller's notification inbox (see utils/inbox.py). Always the caller's own: there is no way to name another player."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..database import models
from ..utils import inbox

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    dependencies=[Depends(auth.get_current_active_user)],
)

PAGE_MAX = 200


def _mine(user: models.User):
    return models.UserNotification.user_id == user.id


@router.get("/")
def list_notifications(
    limit: int = Query(100, ge=1, le=PAGE_MAX),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The newest notices first, and how many are unread."""
    rows = (
        db.query(models.UserNotification)
        .filter(_mine(current_user))
        .order_by(models.UserNotification.created_at.desc(), models.UserNotification.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "unread": _unread(db, current_user),
        "items": [
            {"id": r.id, "title": r.title, "body": r.body, "url": r.url, "created_at": r.created_at, "read": r.read_at is not None}
            for r in rows
        ],
    }


def _unread(db: Session, user: models.User) -> int:
    return (
        db.query(func.count(models.UserNotification.id))
        .filter(_mine(user), models.UserNotification.read_at.is_(None))
        .scalar()
    )


@router.get("/unread")
def unread_count(current_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    return {"unread": _unread(db, current_user)}


@router.post("/read")
def mark_read(current_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Mark every notice of the caller as read."""
    inbox.mark_all_read(db, current_user.id)
    return {"unread": 0}


@router.delete("/{notification_id}")
def delete_one(
    notification_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    deleted = db.execute(
        delete(models.UserNotification).where(models.UserNotification.id == notification_id, _mine(current_user))
    ).rowcount
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Aviso no encontrado")
    return {"deleted": 1}


@router.delete("/")
def delete_all(current_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Empty the caller's inbox."""
    deleted = db.execute(delete(models.UserNotification).where(_mine(current_user))).rowcount
    db.commit()
    return {"deleted": deleted}
