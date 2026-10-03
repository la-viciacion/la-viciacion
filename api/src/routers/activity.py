from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import activity

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
    db: Session = Depends(get_db),
):
    """The latest activity of the group, newest first (derived, nothing stored); `has_more` says if there is more"""
    return activity.feed(db, limit, offset)
