"""Achievements: the catalogue, what each player has unlocked and the full recalculation."""
import datetime
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ...auth import get_db
from ...crud import achievements_recalc
from ...database import models
from ...utils.achievements import is_lifetime
from .common import commit, get_or_404, ordered, router


@router.get("/recalculate-achievements/preview")
def preview_recalculate_achievements(
    user_ids: Optional[list[int]] = Query(None),
    season_list: Optional[list[int]] = Query(None),
    achievement_keys: Optional[list[str]] = Query(None),
    db: Session = Depends(get_db),
):
    """What recalculating the achievements would change (add, correct, revoke), for all the players, seasons
    and achievements that are switched on or only the ones given. It changes nothing."""
    return achievements_recalc.preview(db, user_ids, season_list, achievement_keys)


RECALCULATE_ACHIEVEMENTS_PHRASE = "RECALCULAR"


class RecalculateAchievementsBody(BaseModel):
    user_ids: Optional[list[int]] = Field(None, min_length=1)  # none: every player
    season_list: Optional[list[int]] = Field(None, min_length=1)  # none: every season
    achievement_keys: Optional[list[str]] = Field(None, min_length=1)  # none: every achievement that is switched on
    confirm: str  # must equal RECALCULATE_ACHIEVEMENTS_PHRASE (the panel shows the preview first and asks for it)


@router.post("/recalculate-achievements", status_code=202)
def recalculate_achievements(body: RecalculateAchievementsBody, background_tasks: BackgroundTasks):
    """Work out again the achievements of every player, season and achievement that is switched on, or only the
    ones given, and bring what is stored to it (in background). It never notifies anybody. It rewrites dates and revokes, so it has to be confirmed explicitly."""
    if body.confirm != RECALCULATE_ACHIEVEMENTS_PHRASE:
        raise HTTPException(status_code=400, detail="Confirmación incorrecta")
    background_tasks.add_task(achievements_recalc.recalculate, body.user_ids, body.season_list, body.achievement_keys)
    return {"message": "Recálculo en marcha"}


# ── Achievements ────────────────────────────────────────────────


@router.get("/achievements")
def list_achievements(db: Session = Depends(get_db)):
    awarded = dict(
        db.query(models.UserAchievement.achievement_id, func.count(models.UserAchievement.id))
        .group_by(models.UserAchievement.achievement_id)
        .all()
    )
    rows = db.query(
        models.Achievement.id,
        models.Achievement.key,
        models.Achievement.title,
        models.Achievement.message,
        (models.Achievement.image.isnot(None)).label("has_image"),
        models.Achievement.active,
        models.Achievement.secret,
        models.Achievement.special,
        models.Achievement.valid_from_season,
    ).order_by(models.Achievement.id)
    return [
        {
            "id": r.id,
            "key": r.key,
            "title": r.title,
            "message": r.message,
            "has_image": bool(r.has_image),
            "active": bool(r.active),
            "secret": bool(r.secret),
            "special": r.special,
            "lifetime": is_lifetime(r.key),
            "valid_from_season": r.valid_from_season,
            "awarded": awarded.get(r.id, 0),
        }
        for r in rows
    ]


class AchievementPatch(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    active: Optional[bool] = None  # switched off: not earned, announced, recalculated or shown
    secret: Optional[bool] = None  # hidden until unlocked; announced to the group without saying which, and to the player in full, privately
    special: Optional[int] = Field(None, ge=0, le=3)  # 0 ordinary; 1 silver, 2 gold, 3 purple aura
    valid_from_season: Optional[int] = Field(None, ge=2000, le=2100)  # the first season it can be earned


@router.patch("/achievements/{achievement_id}")
def patch_achievement(achievement_id: int, body: AchievementPatch, db: Session = Depends(get_db)):
    ach = get_or_404(db, models.Achievement, achievement_id, "Logro")
    for k, v in body.model_dump(exclude_unset=True).items():
        if k in ("active", "secret", "special", "valid_from_season") and v is None:
            continue  # they cannot be empty
        setattr(ach, k, v)
    db.commit()
    return {
        "id": ach.id, "key": ach.key, "title": ach.title, "message": ach.message,
        "active": bool(ach.active), "secret": bool(ach.secret), "special": ach.special, "valid_from_season": ach.valid_from_season,
    }


# ── Awarded achievements (what each player has unlocked) ────────


def _award_out(ua: models.UserAchievement, username, ach, game_name) -> dict:
    return {
        "id": ua.id,
        "user_id": ua.user_id,
        "user": username,
        "achievement_id": ua.achievement_id,
        "key": ach.key if ach else None,
        "title": ach.title if ach else None,
        "game_id": ua.game_id,
        "game": game_name,
        "date": ua.date,
        "season": ua.season,
    }


@router.get("/user-achievements")
def list_user_achievements(
    user_id: Optional[int] = None,
    game_id: Optional[str] = None,
    achievement_id: Optional[int] = None,
    season: Optional[int] = None,
    sort: str = Query("date", pattern="^(user|achievement|game|date|season)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = (
        db.query(models.UserAchievement, models.User.username, models.Achievement, models.Game.name)
        .outerjoin(models.User, models.User.id == models.UserAchievement.user_id)
        .outerjoin(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
        .outerjoin(models.Game, models.Game.id == models.UserAchievement.game_id)
    )
    if user_id is not None:
        q = q.filter(models.UserAchievement.user_id == user_id)
    if game_id:
        q = q.filter(models.UserAchievement.game_id == game_id)
    if achievement_id is not None:
        q = q.filter(models.UserAchievement.achievement_id == achievement_id)
    if season is not None:
        q = q.filter(models.UserAchievement.season == season)
    total = q.count()
    columns = {
        "user": models.User.username,
        "achievement": models.Achievement.title,
        "game": models.Game.name,
        "date": models.UserAchievement.date,
        "season": models.UserAchievement.season,
    }
    rows = ordered(q, columns[sort], order, models.UserAchievement.id).limit(limit).offset(offset).all()
    return {"total": total, "items": [_award_out(*row) for row in rows]}


class UserAchievementPatch(BaseModel):
    date: datetime.date


@router.patch("/user-achievements/{award_id}")
def patch_user_achievement(award_id: int, body: UserAchievementPatch, db: Session = Depends(get_db)):
    """Change the date an achievement was unlocked (its year decides the season)."""
    ua = get_or_404(db, models.UserAchievement, award_id, "Logro concedido")
    ua.date = body.date
    commit(db, "Logro concedido")
    db.refresh(ua)
    return _award_out(ua, None, None, None)


@router.delete("/user-achievements/{award_id}")
def revoke_user_achievement(award_id: int, db: Session = Depends(get_db)):
    """Revoke an unlocked achievement. Nothing is announced. If the player still meets its
    condition, the next achievement check unlocks it again: fix the data behind it first."""
    ua = get_or_404(db, models.UserAchievement, award_id, "Logro concedido")
    db.delete(ua)
    db.commit()
    return {"message": "Logro revocado"}
