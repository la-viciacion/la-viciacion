import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import group, wishlist
from ..database import models
from ..utils import seasons

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


@router.get("/players")
def get_players(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The players of the group with their figures and what they are playing now (derived, nothing stored)"""
    return group.players(db, current_user.id)


@router.get("/players/{player_id}")
def get_player(
    player_id: int,
    season: str | None = Query(None, pattern=r"^(all|\d{4})$", description="A year, or 'all' for the totals; default: the running season"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """What is public of a player, readable by every logged-in user on purpose: figures, most played games and
    ratings, achievements and what they play now; never the email, the Telegram id, the settings or the library"""
    found = group.player_profile(
        db, current_user.id, player_id, seasons.ALL if season == "all" else int(season) if season else None,
    )
    if found is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return found


@router.get("/wishlist")
def get_wishlist(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Your wishlist: the games not released yet (the nearest first) and the ones you can already play, each with
    the other players who want it (derived; only the wish is stored)"""
    return wishlist.wishlist(db, current_user.id, datetime.date.today())
