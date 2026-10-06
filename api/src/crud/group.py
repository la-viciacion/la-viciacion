"""What the group has in common, derived when asked (nothing stored): the achievements and who has them, the
players and what is public of each one. Only active players count (never the emergency account)."""
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import time_entries, users


def describe(message: str | None) -> str:
    """The text an achievement announces ("*{}* acaba de jugar 8 horas a _{}_") read as a description: the player
    becomes "alguien", the game "un juego", and the Telegram markup goes."""
    text = message or ""
    for placeholder in ("alguien", "un juego"):
        text = text.replace("{}", placeholder, 1)
    text = text.replace("{}", "")
    text = re.sub(r"[*_]", "", text).strip()
    return text[:1].upper() + text[1:]


def unlocked_ids(db: Session, user_id: int) -> set[int]:
    """The achievements a player has unlocked in any season. Everything about the others stays hidden from them."""
    return {a for (a,) in db.query(models.UserAchievement.achievement_id).filter(models.UserAchievement.user_id == user_id)}


def achievements_catalog(db: Session, viewer_id: int) -> list[dict]:
    """Every achievement with who has unlocked it (and how many times: once per season) and when last. The ones the
    viewer has not unlocked come hidden: no key, title, description, picture or players, only that they exist."""
    mine = unlocked_ids(db, viewer_id)
    players = (models.User.is_active == 1, models.not_god())
    unlocked: dict[int, dict[int, dict]] = {}
    for achievement_id, user_id, username, name, date in (
        db.query(models.UserAchievement.achievement_id, models.UserAchievement.user_id, models.User.username, models.User.name,
                 models.UserAchievement.date)
        .join(models.User, models.UserAchievement.user_id == models.User.id)
        .filter(*players)
    ):
        who = unlocked.setdefault(achievement_id, {}).setdefault(
            user_id, {"user_id": user_id, "name": name or username, "times": 0, "last": date},
        )
        who["times"] += 1
        if date > who["last"]:
            who["last"] = date

    catalog = []
    for row in db.query(
        models.Achievement.id, models.Achievement.key, models.Achievement.title, models.Achievement.message,
        models.Achievement.image.isnot(None).label("has_image"), models.Achievement.active,
    ).order_by(models.Achievement.id):
        if not row.active and row.id not in mine:
            continue  # switched off: it does not exist yet, not even as a hidden one
        if row.id not in mine:
            catalog.append({"id": row.id, "hidden": True, "unlocked_by_me": False})
            continue
        who = sorted(unlocked.get(row.id, {}).values(), key=lambda w: (w["last"], w["name"].lower()), reverse=True)
        catalog.append({
            "id": row.id,
            "hidden": False,
            "key": row.key,
            "title": row.title,
            "description": describe(row.message),
            "has_image": bool(row.has_image),
            "unlocked_by": len(who),
            "unlocked_by_me": True,
            "players": who,
        })
    return catalog


def _playing_now(db: Session, viewer_id: int) -> dict[int, dict]:
    """user_id -> the running timer to show (fresh, and not hidden by the player: see get_now_playing)."""
    return {p["user_id"]: p for p in time_entries.get_now_playing(db, viewer_id) if not p["stale"]}


def players(db: Session, viewer_id: int) -> list[dict]:
    """The players of the group with their figures (every season) and what they are playing now; the ones playing
    first, then the latest to play, then by name."""
    active = (models.User.is_active == 1, models.not_god())
    time = {
        user_id: (int(seconds or 0), last)  # MariaDB returns SUM() as Decimal
        for user_id, seconds, last in db.query(
            models.GameTimer.user_id, func.sum(models.GameTimer.duration_seconds), func.max(models.GameTimer.start_time)
        ).group_by(models.GameTimer.user_id)
    }
    games: dict[int, set[str]] = {}
    completed: dict[int, int] = {}
    for user_id, game_id, done in db.query(models.UserGame.user_id, models.UserGame.game_id, models.UserGame.completed):
        games.setdefault(user_id, set()).add(game_id)
        if done:
            completed[user_id] = completed.get(user_id, 0) + 1
    awards = dict(
        db.query(models.UserAchievement.user_id, func.count(models.UserAchievement.id)).group_by(models.UserAchievement.user_id)
    )
    playing = _playing_now(db, viewer_id)

    rows = []
    for user in db.query(models.User).filter(*active):
        seconds, last = time.get(user.id, (0, None))
        rows.append({
            "user_id": user.id,
            "username": user.username,
            "name": user.name or user.username,
            "played_seconds": seconds,
            "games": len(games.get(user.id, ())),
            "completed": completed.get(user.id, 0),
            "achievements": awards.get(user.id, 0),
            "last_played": last,
            "playing": playing.get(user.id),
            "is_me": user.id == viewer_id,
        })
    rows.sort(key=lambda r: (r["playing"] is None, -(r["last_played"].timestamp() if r["last_played"] else 0), r["name"].lower()))
    return rows


def player_profile(db: Session, viewer_id: int, player_id: int, season=None) -> dict | None:
    """What is public of a player: name, figures of a season (or all of them), most played games with their
    ratings, streaks, latest achievements and what they are playing now. Never the email, the Telegram id, the
    settings or the library. None if there is no such active player."""
    user = (
        db.query(models.User)
        .filter(models.User.id == player_id, models.User.is_active == 1, models.not_god())
        .first()
    )
    if user is None:
        return None
    data = users.get_profile(db, user, season)
    mine = unlocked_ids(db, viewer_id)
    achievements = [
        {"title": a["title"], "date": a["date"], "hidden": False} if a["id"] in mine else {"hidden": True, "date": a["date"]}
        for a in data["achievements"]
    ]
    return {
        "user": {"id": user.id, "username": user.username, "name": user.name or user.username},
        "season": data["season"],
        "seasons": data["seasons"],
        "stats": data["stats"],
        "top_games": data["top_games"],
        "achievements": achievements,
        "playing": _playing_now(db, viewer_id).get(user.id),
        "is_me": user.id == viewer_id,
    }
