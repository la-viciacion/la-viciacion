"""The latest things the group has done, newest first: hours played, games started, completed and rated,
achievements unlocked. Derived from the sessions, the library, the ratings and the achievements when asked;
nothing is stored. Every player counts, active or not (never the emergency account)."""
import datetime

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..database import models
from . import group

# Events at the very same moment come in this order
RANK = {"completed": 0, "achievement": 1, "rated": 2, "started": 3, "played": 4}


def _day(value) -> datetime.date:
    """SQLite hands back text, MariaDB a date."""
    if isinstance(value, datetime.datetime):
        return value.date()
    return value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value))


def _moment(value) -> datetime.datetime:
    """SQLite hands back text for an aggregate, MariaDB a datetime."""
    return value if isinstance(value, datetime.datetime) else datetime.datetime.fromisoformat(str(value))


def _place_in_time(db: Session, events: list[dict]) -> None:
    """Gives every event its `at`, the moment it is sorted by. Sessions and ratings carry a real time; a game
    started, completed or an achievement only has a day, so it is placed against the player's sessions of that
    day: a start right before the first session of that game, a completion or an achievement right after the
    last session (of that game, or of the day). Without sessions that day, a start is the first moment of the
    day and the rest the last."""
    days = {e["day"] for e in events}
    first: dict[tuple, datetime.datetime] = {}  # (user, game, day) -> start of its first session
    last: dict[tuple, datetime.datetime] = {}  # (user, game, day) -> end of its last session
    last_of_day: dict[tuple, datetime.datetime] = {}  # (user, day) -> end of their last session
    if days:
        played_day = func.date(models.GameTimer.start_time)
        for user_id, game_id, day, begin, end in (
            db.query(
                models.GameTimer.user_id, models.GameTimer.game_id, played_day, func.min(models.GameTimer.start_time),
                func.max(func.coalesce(models.GameTimer.end_time, models.GameTimer.start_time)),
            )
            .filter(models.GameTimer.is_active == False, played_day.in_([d.isoformat() for d in days]))  # noqa: E712
            .group_by(models.GameTimer.user_id, models.GameTimer.game_id, played_day)
        ):
            day, begin, end = _day(day), _moment(begin), _moment(end)
            first[user_id, game_id, day], last[user_id, game_id, day] = begin, end
            if end > last_of_day.get((user_id, day), datetime.datetime.min):
                last_of_day[user_id, day] = end

    second = datetime.timedelta(seconds=1)
    for e in events:
        if "at" in e:
            continue
        key = (e["user_id"], e["game_id"], e["day"])
        day_start = datetime.datetime.combine(e["day"], datetime.time.min)
        day_end = datetime.datetime.combine(e["day"], datetime.time.max).replace(microsecond=0)
        after_day = last_of_day[e["user_id"], e["day"]] + second if (e["user_id"], e["day"]) in last_of_day else day_end
        if e["type"] == "started":
            e["at"] = first[key] - second if key in first else day_start
        elif e["type"] == "completed":
            e["at"] = last[key] + second if key in last else after_day
        else:  # achievement
            e["at"] = after_day


def feed(db: Session, viewer_id: int, limit: int = 30, offset: int = 0) -> dict:
    """`limit` events from `offset`, and whether there are more. Every source gives its newest
    `offset + limit + 1` rows, which is enough to know the newest ones of the merge. The secret achievements the
    viewer has not unlocked are announced without saying which."""
    n = offset + limit + 1
    mine = group.unlocked_ids(db, viewer_id)
    players = (models.not_god(),)
    ratings = {(u, g): s for u, g, s in db.query(models.GameScore.user_id, models.GameScore.game_id, models.GameScore.score)}
    events: list[dict] = []

    def add(kind, day, user_id, name, username, game_id=None, game_name=None, image_url=None, **extra):
        events.append({
            "type": kind, "day": _day(day), "user_id": user_id, "name": name or username, "game_id": game_id,
            "game_name": game_name, "image_url": image_url, **extra,
        })

    for timer, name, username, game_name, image in (
        db.query(models.GameTimer, models.User.name, models.User.username, models.Game.name, models.Game.image_url)
        .join(models.User, models.GameTimer.user_id == models.User.id)
        .join(models.Game, models.GameTimer.game_id == models.Game.id)
        .filter(models.GameTimer.is_active == False, *players)  # noqa: E712
        .order_by(desc(models.GameTimer.start_time), models.GameTimer.user_id, models.GameTimer.game_id)
        .limit(n)
    ):
        # a session that crosses midnight stays on the day it began, so the days of the list never interleave
        day = timer.start_time.date()
        end_of_day = datetime.datetime.combine(day, datetime.time.max).replace(microsecond=0)
        add("played", day, timer.user_id, name, username, timer.game_id, game_name, image,
            seconds=int(timer.duration_seconds or 0), at=min(timer.end_time or timer.start_time, end_of_day))

    for user_id, game_id, day, name, username, game_name, image in (
        db.query(
            models.UserGame.user_id, models.UserGame.game_id, func.min(models.UserGame.started_date).label("day"),
            models.User.name, models.User.username, models.Game.name, models.Game.image_url,
        )
        .join(models.User, models.UserGame.user_id == models.User.id)
        .join(models.Game, models.UserGame.game_id == models.Game.id)
        .filter(*players)
        .group_by(models.UserGame.user_id, models.UserGame.game_id, models.User.name, models.User.username,
                  models.Game.name, models.Game.image_url)
        .order_by(desc("day"), models.UserGame.user_id, models.UserGame.game_id)
        .limit(n)
    ):
        add("started", day, user_id, name, username, game_id, game_name, image)

    for entry, name, username, game_name, image in (
        db.query(models.UserGame, models.User.name, models.User.username, models.Game.name, models.Game.image_url)
        .join(models.User, models.UserGame.user_id == models.User.id)
        .join(models.Game, models.UserGame.game_id == models.Game.id)
        .filter(models.UserGame.completed == 1, models.UserGame.completed_date.isnot(None), *players)
        .order_by(desc(models.UserGame.completed_date), models.UserGame.user_id, models.UserGame.game_id)
        .limit(n)
    ):
        add("completed", entry.completed_date, entry.user_id, name, username, entry.game_id, game_name, image,
            score=ratings.get((entry.user_id, entry.game_id)))

    for rating, name, username, game_name, image in (
        db.query(models.GameScore, models.User.name, models.User.username, models.Game.name, models.Game.image_url)
        .join(models.User, models.GameScore.user_id == models.User.id)
        .join(models.Game, models.GameScore.game_id == models.Game.id)
        .filter(*players)
        .order_by(desc(models.GameScore.updated_at), models.GameScore.user_id, models.GameScore.game_id)
        .limit(n)
    ):
        add("rated", rating.updated_at, rating.user_id, name, username, rating.game_id, game_name, image, score=rating.score, at=rating.updated_at)

    for award, name, username, title, secret, game_id, game_name, image in (
        db.query(models.UserAchievement, models.User.name, models.User.username, models.Achievement.title,
                 models.Achievement.is_secret, models.UserAchievement.game_id, models.Game.name, models.Game.image_url)
        .join(models.User, models.UserAchievement.user_id == models.User.id)
        .join(models.Achievement, models.UserAchievement.achievement_id == models.Achievement.id)
        .outerjoin(models.Game, models.UserAchievement.game_id == models.Game.id)
        .filter(*players)
        .order_by(desc(models.UserAchievement.date), models.UserAchievement.user_id, models.UserAchievement.achievement_id)
        .limit(n)
    ):
        # a secret one the viewer has not unlocked stays hidden: no title, and the game would give it away
        seen = award.achievement_id in mine or not secret
        add("achievement", award.date, award.user_id, name, username, game_id if seen else None,
            game_name if seen else None, image if seen else None, title=title if seen else None, hidden=not seen)

    _place_in_time(db, events)
    events.sort(key=lambda e: (-e["at"].timestamp(), RANK[e["type"]], e["user_id"], e["game_id"] or "", e.get("title") or ""))
    page = events[offset:offset + limit]
    for e in page:
        del e["at"]
    return {"items": page, "has_more": len(events) > offset + limit}
