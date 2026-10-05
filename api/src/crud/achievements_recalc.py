"""Recalculation of every achievement of every player and season (admin).

The live checks only ever add what a player has just earned. This works out, from the sessions and the
library as they are now, everything each player deserves in each season, with the very rules of the live
checks (`Achievements` in `collected` mode), and brings what is stored to that: it adds what is missing,
corrects the date and game of what differs and revokes what no longer holds. Everybody counts, active or
not (they may have been in a past season). The emergency account never does.

It never notifies anybody: it neither goes through `send_message` nor can be asked to (see
`Achievements.collected`). A preview (`plan`) lists the changes without making them; applying them is a
second step.
"""
import asyncio
import datetime
from typing import NamedTuple

from sqlalchemy.orm import Session

from ..database import models
from ..utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from ..utils.logger import LogManager
from .achievements import Achievements, Award

logger = LogManager().get_logger()

TEAMWORK_PLAYERS = 4


class Change(NamedTuple):
    action: str  # "add" | "date" (the date or the game of what is stored differs) | "revoke"
    user_id: int
    user: str
    season: int
    key: str
    title: str
    date_before: datetime.date | None
    date_after: datetime.date | None
    game_before: str | None
    game_after: str | None
    rows: tuple  # ids of the stored rows it touches

    def as_dict(self) -> dict:
        data = self._asdict()
        data["rows"] = list(self.rows)
        return data


def teamwork_dates(db: Session, season: int, now: datetime.datetime | None = None) -> dict[int, datetime.date]:
    """{user_id: the day they first played with at least three others at once in the season}.

    It is the sessions that overlap, whoever the players and whatever the session: a timer still running
    counts until now, and so does one that was forgotten (they cannot be told apart yet)."""
    now = now or datetime.datetime.now()
    rows = (
        db.query(models.GameTimer.user_id, models.GameTimer.start_time, models.GameTimer.end_time)
        .join(models.User, models.User.id == models.GameTimer.user_id)
        .filter(models.GameTimer.season == season, models.not_god())
        .all()
    )
    dates: dict[int, datetime.date] = {}
    running: list[tuple[datetime.datetime, int]] = []  # (end, user) of the sessions on at the moment
    for user_id, start, end in sorted(rows, key=lambda row: row[1]):
        running = [(until, other) for until, other in running if until > start]
        running.append((end or now, user_id))
        together = {other for _, other in running}
        if len(together) >= TEAMWORK_PLAYERS:
            for other in together:
                dates.setdefault(other, start.date())
    return dates


def _seasons_of(db: Session, user_id: int) -> set[int]:
    """The seasons the user has something in: a session, a library entry or an achievement."""
    found: set[int] = set()
    for model in (models.GameTimer, models.UserGame, models.UserAchievement):
        found.update(year for (year,) in db.query(model.season).filter(model.user_id == user_id).distinct() if year)
    return found


async def _expected(db: Session, user: models.User, season: int) -> dict[str, Award]:
    """What the user deserves in the season: {achievement key: Award}."""
    collected: list[Award] = []
    checks = Achievements(silent=True, season=season, collected=collected)
    await actions.check_user(db, user, silent=True, checks=checks)
    await checks.opened_by_mistake_from_sessions(db, user)
    await checks.just_in_time_of_the_season(db, user)
    return {award.key: award for award in collected}


def _diff(user: models.User, season: int, expected: dict[str, Award], stored: list, titles: dict[str, str]) -> list[Change]:
    by_key: dict[str, list] = {}
    for row in stored:
        by_key.setdefault(row.key, []).append(row)
    changes = []

    def change(action, key, row=None, award=None, rows=()):
        return Change(
            action, user.id, user.name, season, key, titles.get(key, key),
            row.date if row else None, award.date if award else None,
            row.game_id if row else None, award.game_id if award else None, tuple(rows),
        )

    for key, award in expected.items():
        rows = by_key.pop(key, [])
        if not rows:
            changes.append(change("add", key, award=award))
            continue
        first, *repeated = rows
        if (first.date, first.game_id) != (award.date, award.game_id):
            changes.append(change("date", key, first, award, [first.id]))
        changes.extend(change("revoke", key, row, None, [row.id]) for row in repeated)  # one per season
    for key, rows in by_key.items():
        changes.extend(change("revoke", key, row, None, [row.id]) for row in rows)
    return changes


async def _plan(db: Session, user_id: int | None, only_seasons: set[int] | None = None) -> list[Change]:
    query = db.query(models.User).filter(models.not_god())
    if user_id is not None:
        query = query.filter(models.User.id == user_id)
    titles = {key: title for key, title in db.query(models.Achievement.key, models.Achievement.title).all()}
    teamwork: dict[int, dict[int, datetime.date]] = {}  # season -> user -> day
    changes: list[Change] = []
    for user in query.order_by(models.User.id).all():
        for season in sorted(_seasons_of(db, user.id) if only_seasons is None else _seasons_of(db, user.id) & only_seasons):
            expected = await _expected(db, user, season)
            if season not in teamwork:
                teamwork[season] = teamwork_dates(db, season)
            if user.id in teamwork[season]:
                expected["TEAMWORK"] = Award(user.id, "TEAMWORK", teamwork[season][user.id], None)
            stored = (
                db.query(models.UserAchievement.id, models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id)
                .join(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
                .filter(models.UserAchievement.user_id == user.id, models.UserAchievement.season == season)
                .order_by(models.UserAchievement.id)
                .all()
            )
            changes.extend(_diff(user, season, expected, stored, titles))
    return changes


def plan(db: Session, user_id: int | None = None) -> list[Change]:
    """What a recalculation would change, for everybody or one user. It changes nothing."""
    return asyncio.run(_plan(db, user_id))


async def recalculate_user(db: Session, user_id: int, season_list: list[int]) -> list[Change]:
    """Work out again the achievements of one user in some seasons and apply it, in silence. It is what
    follows a session that was edited or deleted: what it earned and no longer holds is revoked. The
    caller is already in an event loop and holds the lock of the checks."""
    changes = await _plan(db, user_id, set(season_list))
    apply(db, changes)
    return changes


def preview(db: Session, user_id: int | None = None) -> dict:
    changes = plan(db, user_id)
    counts = {action: sum(1 for change in changes if change.action == action) for action in ("add", "date", "revoke")}
    return {"counts": counts, "changes": [change.as_dict() for change in changes]}


def apply(db: Session, changes: list[Change]) -> None:
    """Make the changes, all or none."""
    ids = {key: id_ for id_, key in db.query(models.Achievement.id, models.Achievement.key).all()}
    try:
        for change in changes:
            if change.action == "add":
                db.add(models.UserAchievement(
                    user_id=change.user_id, achievement_id=ids[change.key], date=change.date_after, game_id=change.game_after,
                ))
            elif change.action == "date":
                db.query(models.UserAchievement).filter(models.UserAchievement.id.in_(change.rows)).update(
                    {"date": change.date_after, "game_id": change.game_after}, synchronize_session=False
                )
            else:
                db.query(models.UserAchievement).filter(models.UserAchievement.id.in_(change.rows)).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise


def recalculate(user_id: int | None = None) -> None:
    """Background-task entrypoint of the admin panel: work everything out again and apply it, in silence.

    Under the lock of the other checks, with its own DB session, like the rest of the follow-ups."""
    from ..database.database import SessionLocal

    with actions._check_lock:
        try:
            with SessionLocal() as db:
                changes = plan(db, user_id)
                apply(db, changes)
            logger.info(f"Achievements recalculated: {len(changes)} changes")
        except Exception as e:
            logger.error("Error recalculating the achievements: " + str(e))
