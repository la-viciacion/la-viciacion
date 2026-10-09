"""What the group has in common, derived when asked (nothing stored): the achievements and who has them, the
players and what is public of each one. Every player is listed, active or not (an inactive one cannot log in or act, nothing more; never the
emergency account), and who has an achievement counts everybody who earned it."""
import datetime
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import affinity, time_entries, users
from .achievement_progress import Progress
from ..utils.achievements import is_lifetime  # after the crud modules: they import each other
from ..utils import seasons


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


def unlocked_in_season(db: Session, user_id: int, season: int) -> set[int]:
    return {
        a for (a,) in db.query(models.UserAchievement.achievement_id).filter(
            models.UserAchievement.user_id == user_id, models.UserAchievement.season == season
        )
    }


def achievements_catalog(db: Session, viewer_id: int, today: datetime.date | None = None, season: int | None = None) -> list[dict]:
    """Every achievement with who has unlocked it and when last. The ones the viewer has not unlocked come with
    their name and picture but **no description** (the front dims them: the player has to work out what they are
    about) unless they are secret: those come hidden, with no key, title, description or picture (and of the players only their names, no dates), only that
    they exist, whether they are secret and their special level (so that everybody knows there are special ones to
    unlock). One that is switched on but not valid yet (`valid_from_season` in the future), secret or not, is listed
    that way too, in the running season, so it is already there as a hidden one when it begins to count. Whoever has unlocked an achievement once knows what it is: that is what shows the description and
    lifts the secrecy, whatever the season on screen. The same goes for its key and its picture, which would
    give away what it is about: they are only sent for the ones the viewer has unlocked at some point.

    `season` (default: the running one) is the season of the season achievements, which are earned once a season:
    only the ones valid in it are listed, and what is said of each (who has it, whether the viewer has it, the
    progress) is about that season. The lifetime ones are earned once and do not depend on it. The ones that add
    something up (hours, days, games, completions, a streak) come with the viewer's `progress` towards them, until
    they have them, but only for the running season: a closed one cannot be played any more."""
    season = season or seasons.current()
    known = unlocked_ids(db, viewer_id)
    mine_in_season = unlocked_in_season(db, viewer_id, season)
    progress = Progress(db, viewer_id, today)

    achievements = db.query(
        models.Achievement.id, models.Achievement.key, models.Achievement.title, models.Achievement.message,
        models.Achievement.image.isnot(None).label("has_image"), models.Achievement.active, models.Achievement.is_secret.label("secret"),
        models.Achievement.special, models.Achievement.valid_from_season,
    ).order_by(models.Achievement.id).all()
    lifetime_ids = {a.id for a in achievements if is_lifetime(a.key)}

    unlocked: dict[int, dict[int, dict]] = {}
    for achievement_id, user_id, username, name, date, award_season in (
        db.query(models.UserAchievement.achievement_id, models.UserAchievement.user_id, models.User.username, models.User.name,
                 models.UserAchievement.date, models.UserAchievement.season)
        .join(models.User, models.UserAchievement.user_id == models.User.id)
        .filter(models.not_god())  # whoever earned it counts, even if they no longer play
    ):
        if achievement_id not in lifetime_ids and award_season != season:
            continue
        who = unlocked.setdefault(achievement_id, {}).setdefault(
            user_id, {"user_id": user_id, "name": name or username, "times": 0, "last": date},
        )
        who["times"] += 1
        if date > who["last"]:
            who["last"] = date

    catalog = []
    for row in achievements:
        lifetime = row.id in lifetime_ids
        mine = row.id in (known if lifetime else mine_in_season)
        listed_in = seasons.current() if lifetime else season
        # one that is switched on but starts to count in a later season is listed as a hidden one, secret or not, in the
        # running season (with its aura, if it is special): nobody has it and nobody can tell what it is, and when its
        # season comes the usual rules apply
        upcoming = row.active and row.valid_from_season > listed_in and listed_in == seasons.current()
        if (not row.active or row.valid_from_season > listed_in) and not mine and not upcoming:
            continue  # switched off, or not valid yet: it does not exist yet, not even as a hidden one
        who = sorted(unlocked.get(row.id, {}).values(), key=lambda w: (w["last"], w["name"].lower()), reverse=True)
        if row.id not in known and (row.secret or upcoming):
            catalog.append({
                "id": row.id, "hidden": True, "unlocked_by_me": False, "secret": bool(row.secret), "special": row.special,
                "lifetime": lifetime,  # which block of the page it goes in; says nothing about what it is
                # the only thing a hidden one says: who has it (no date, no times), so that it is seen to be possible
                "unlocked_by": len(who),
                "players": [{"user_id": w["user_id"], "name": w["name"]} for w in who],
            })
            continue
        is_known = row.id in known
        catalog.append({
            "id": row.id,
            "hidden": False,
            # the key names the achievement and its picture shows what it is about: neither is given to whoever has
            # never unlocked it (the front shows a placeholder instead)
            "key": row.key if is_known else None,
            "title": row.title,
            "description": describe(row.message) if is_known else None,  # what it is about is for whoever earns it
            "secret": bool(row.secret),
            "special": row.special,
            "lifetime": lifetime,  # earned once in a lifetime, not once a season
            "progress": None if mine or (not lifetime and season != seasons.current())
            else progress.of(row.key, row.valid_from_season, lifetime),
            "has_image": bool(row.has_image) and is_known,
            "unlocked_by": len(who),
            "unlocked_by_me": mine,
            "players": who,
        })
    return catalog


def _playing_now(db: Session, viewer_id: int) -> dict[int, dict]:
    """user_id -> the running timer to show (fresh, and not hidden by the player: see get_now_playing)."""
    return {p["user_id"]: p for p in time_entries.get_now_playing(db, viewer_id) if not p["stale"]}


def players(db: Session, viewer_id: int) -> list[dict]:
    """The players of the group with their figures (every season) and what they are playing now; the ones playing
    first, then the latest to play, then by name."""
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
    for user in db.query(models.User).filter(models.not_god()):
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
            "is_active": bool(user.is_active),
            "is_me": user.id == viewer_id,
        })
    rows.sort(key=lambda r: (r["playing"] is None, -(r["last_played"].timestamp() if r["last_played"] else 0), r["name"].lower()))
    return rows


def player_profile(db: Session, viewer_id: int, player_id: int, season=None) -> dict | None:
    """What is public of a player: name, figures of a season (or all of them), most played games with their
    ratings, streaks, latest achievements and what they are playing now. Never the email, the Telegram id, the
    settings or the library. None if there is no such player."""
    user = (
        db.query(models.User)
        .filter(models.User.id == player_id, models.not_god())
        .first()
    )
    if user is None:
        return None
    data = users.get_profile(db, user, season)
    mine = unlocked_ids(db, viewer_id)
    achievements = [
        {"title": a["title"], "date": a["date"], "hidden": False, "secret": a["secret"], "special": a["special"]}
        if a["id"] in mine or not a["secret"] else {"hidden": True, "date": a["date"], "secret": True, "special": a["special"]}
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
        "is_active": bool(user.is_active),
        "is_me": user.id == viewer_id,
        # how alike your taste and theirs are (every season, whatever the one on screen); none for yourself
        "affinity": None if user.id == viewer_id else affinity.between(db, viewer_id, user.id),
    }
