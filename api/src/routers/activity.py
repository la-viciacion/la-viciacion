from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import activity
from ..database import models

router = APIRouter(
    prefix="/activity",
    tags=["Activity"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


@router.get("")
def get_activity(
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The latest activity of the group, newest first (derived, nothing stored); `has_more` says if there is more.
    The achievements the caller has not unlocked come as `hidden`, without title"""
    return activity.feed(db, current_user.id, limit, offset)
