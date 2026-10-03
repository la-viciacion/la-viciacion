from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import group
from ..database import models

router = APIRouter(
    prefix="/group",
    tags=["Group"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


@router.get("/achievements")
def get_achievements(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every achievement with who of the group has unlocked it (derived, nothing stored)"""
    return group.achievements_catalog(db, current_user.id)
