import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import group, group_library, library_compare, wishlist
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
    season: int | None = Query(None, ge=2000, description="The season of the season achievements (default: the running one)"),
    summary: bool = Query(False, description="Every season at once: each season achievement once, with the seasons the viewer earned it in"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every achievement with who of the group has unlocked it (derived, nothing stored)"""
    if season is not None and season > seasons.current():
        raise HTTPException(status_code=400, detail="Esa temporada todavía no existe")
    return group.achievements_catalog(db, current_user.id, season=season, summary=summary)


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


@router.get("/library")
def get_group_library(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The group's library as a whole: hidden gems, the graveyard (games players gave up), rarities (games one player
    has), what nobody has touched and the coverage by genre and platform. Derived from the libraries, the sessions and
    the ratings; readable by every logged-in user on purpose, like the game pages it is made of."""
    return group_library.library(db)


@router.get("/players/{player_id}/compare")
def compare_libraries(
    player_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Your library and another player's side by side: the games you both have (with the hours and the rating of
    each), the ones only you have and the ones only they have, and your affinity. Readable by every logged-in user on
    purpose: it is what each game's page already says (who has it, with their hours and rating), grouped by pair."""
    if player_id == current_user.id:
        raise HTTPException(status_code=400, detail="Elige a otro jugador para comparar")
    player = db.get(models.User, player_id)
    if player is None or player.username == models.GOD_USERNAME:
        raise HTTPException(status_code=404, detail="Player not found")
    return library_compare.compare(db, current_user.id, player)


@router.get("/releases")
def get_releases(
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="A month, YYYY-MM; default: the running one"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The release calendar: every game of the catalogue that comes out in the month, wanted or not and in any
    month, past ones included (readable by every logged-in user on purpose), and the wished ones with no date.
    Derived; only the wishes are stored."""
    today = datetime.date.today()
    year, number = (today.year, today.month) if month is None else (int(month[:4]), int(month[5:]))
    return wishlist.releases(db, current_user.id, year, number, today)


@router.get("/wishlist")
def get_wishlist(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Your wishlist: the games not released yet (the nearest first) and the ones you can already play, each with
    the other players who want it (derived; only the wish is stored)"""
    return wishlist.wishlist(db, current_user.id, datetime.date.today())
