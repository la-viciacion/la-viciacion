"""What the group has in common, derived when asked (nothing stored): the achievements and who has them.
Only active players count (never the emergency account)."""
import re

from sqlalchemy.orm import Session

from ..database import models


def describe(message: str | None) -> str:
    """The text an achievement announces ("*{}* acaba de jugar 8 horas a _{}_") read as a description: the player
    becomes "alguien", the game "un juego", and the Telegram markup goes."""
    text = message or ""
    for placeholder in ("alguien", "un juego"):
        text = text.replace("{}", placeholder, 1)
    text = text.replace("{}", "")
    text = re.sub(r"[*_]", "", text).strip()
    return text[:1].upper() + text[1:]


def achievements_catalog(db: Session, viewer_id: int) -> list[dict]:
    """Every achievement with who has unlocked it (and how many times: once per season) and when last."""
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
        models.Achievement.image.isnot(None).label("has_image"),
    ).order_by(models.Achievement.id):
        who = sorted(unlocked.get(row.id, {}).values(), key=lambda w: (w["last"], w["name"].lower()), reverse=True)
        catalog.append({
            "id": row.id,
            "key": row.key,
            "title": row.title,
            "description": describe(row.message),
            "has_image": bool(row.has_image),
            "unlocked_by": len(who),
            "unlocked_by_me": any(w["user_id"] == viewer_id for w in who),
            "players": who,
        })
    return catalog
