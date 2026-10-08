"""Recalculation of every achievement of every player and season (admin).

The live checks only ever add what a player has just earned. This works out, from the sessions and the
library as they are now, everything each player deserves in each season, with the very rules of the live
checks (`Achievements` in `collected` mode), and brings what is stored to that: it adds what is missing,
corrects the date and game of what differs and revokes what no longer holds. Everybody counts, active or
not (they may have been in a past season). The emergency account never does.

The recalculation of the admin panel never notifies anybody: the working out itself neither goes through
`send_message` nor can be asked to (see `Achievements.collected`). Only the follow-up of a player's own session
(`recalculate_user` with `notify`) announces what it added, once the changes are stored. A preview (`plan`) lists
the changes without making them; applying them is a second step.
"""
import asyncio
import datetime
from typing import NamedTuple

from sqlalchemy.orm import Session

from ..database import models
from ..utils import actions  # noqa: F401  (imported first: the crud and utils modules import each other)
from ..utils import seasons
from ..utils.achievements import is_lifetime
from ..utils.logger import LogManager
from .achievements import ALL_TOGETHER_PLAYERS, Achievements, Award

logger = LogManager().get_logger()

TEAMWORK_PLAYERS = 4
# judged on the timers running together, one message naming everybody: only a timer that starts can announce them
MULTIPLAYER_KEYS = {"TEAMWORK", "ALL_TOGETHER"}


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


def _crowds(
    db: Session, season: int, minimum: int, per_game: bool, now: datetime.datetime | None = None
) -> dict[int, tuple[datetime.date, str | None]]:
    """{user_id: (the day they first played with enough others at once in the season, the game)}.

    It is the sessions that overlap, whoever the players and whatever the session (a manual one cannot be
    told from a timer): one still running counts until now, and so does one that was forgotten (they cannot
    be told apart yet). With `per_game` only the sessions of the same game count together."""
    now = now or datetime.datetime.now()
    rows = (
        db.query(models.GameTimer.user_id, models.GameTimer.game_id, models.GameTimer.start_time, models.GameTimer.end_time)
        .join(models.User, models.User.id == models.GameTimer.user_id)
        .filter(models.GameTimer.season == season, models.not_god())
        .all()
    )
    found: dict[int, tuple[datetime.date, str | None]] = {}
    running: dict[str | None, list[tuple[datetime.datetime, int]]] = {}  # per game: (end, user) of the sessions on
    for user_id, game_id, start, end in sorted(rows, key=lambda row: row[2]):
        key = game_id if per_game else None
        on = [(until, other) for until, other in running.get(key, []) if until > start]
        on.append((end or now, user_id))
        running[key] = on
        together = {other for _, other in on}
        if len(together) >= minimum:
            for other in together:
                found.setdefault(other, (start.date(), key))
    return found


def teamwork_dates(db: Session, season: int, now: datetime.datetime | None = None) -> dict[int, datetime.date]:
    """{user_id: the day they first played with at least three others at once in the season}."""
    return {user_id: day for user_id, (day, _) in _crowds(db, season, TEAMWORK_PLAYERS, False, now).items()}


def all_together_days(db: Session, season: int, now: datetime.datetime | None = None) -> dict[int, tuple[datetime.date, str]]:
    """{user_id: (the day they first played a game with at least two others at once, the game)}."""
    return _crowds(db, season, ALL_TOGETHER_PLAYERS, True, now)


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


async def _expected_lifetime(db: Session, user: models.User) -> tuple[dict[str, Award], set[str]]:
    """What the user deserves of the achievements with no season limit: ({achievement key: Award}, the keys that
    could not be told, because the weather service did not answer, and are left as they are)."""
    collected: list[Award] = []
    undecided: set[str] = set()
    await actions.check_user_lifetime(db, user, silent=True, collected=collected, undecided=undecided)
    return {award.key: award for award in collected}, undecided


def _diff(user: models.User, expected: dict[str, Award], stored: list, titles: dict[str, str], allowed: set[str]) -> list[Change]:
    """What to change to bring `stored` to `expected`, only for the achievements in `allowed` (the ones chosen
    that are switched on): the rest is left exactly as it is. The season of a change is the one of the row it
    touches, or the one the date of what is added falls in."""
    expected = {key: award for key, award in expected.items() if key in allowed}
    by_key: dict[str, list] = {}
    for row in stored:
        if row.key in allowed:
            by_key.setdefault(row.key, []).append(row)
    changes = []

    def change(action, key, row=None, award=None, rows=()):
        return Change(
            action, user.id, user.name, row.season if row else award.date.year, key, titles.get(key, key),
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
        changes.extend(change("revoke", key, row, None, [row.id]) for row in repeated)  # one per season, or one in all
    for key, rows in by_key.items():
        changes.extend(change("revoke", key, row, None, [row.id]) for row in rows)
    return changes


async def _plan(
    db: Session,
    user_ids: list[int] | None = None,
    only_seasons: set[int] | None = None,
    achievement_keys: list[str] | None = None,
) -> list[Change]:
    query = db.query(models.User).filter(models.not_god())
    if user_ids is not None:
        query = query.filter(models.User.id.in_(user_ids))
    titles = {key: title for key, title in db.query(models.Achievement.key, models.Achievement.title).all()}
    switched_on = {key for (key,) in db.query(models.Achievement.key).filter(models.Achievement.active == True)}  # noqa: E712
    allowed = switched_on if achievement_keys is None else switched_on & set(achievement_keys)
    valid_from = dict(db.query(models.Achievement.key, models.Achievement.valid_from_season).all())
    this_season = seasons.current()
    lifetime_keys = {key for key in allowed if is_lifetime(key)}
    allowed -= lifetime_keys  # they have no season: they are worked out apart, once per user
    # one that is not valid yet is left exactly as it is, in a season before its own and now
    lifetime_keys = {key for key in lifetime_keys if valid_from[key] <= this_season}
    stored_rows = (
        db.query(models.UserAchievement.id, models.Achievement.key, models.UserAchievement.date, models.UserAchievement.game_id,
                 models.UserAchievement.season)
        .join(models.Achievement, models.Achievement.id == models.UserAchievement.achievement_id)
        .order_by(models.UserAchievement.id)
    )
    teamwork: dict[int, dict[int, datetime.date]] = {}  # season -> user -> day
    together: dict[int, dict[int, tuple[datetime.date, str]]] = {}  # season -> user -> (day, game)
    changes: list[Change] = []
    for user in query.order_by(models.User.id).all():
        for season in sorted(_seasons_of(db, user.id) if only_seasons is None else _seasons_of(db, user.id) & only_seasons):
            expected = await _expected(db, user, season)
            if season not in teamwork:
                teamwork[season] = teamwork_dates(db, season)
            if user.id in teamwork[season]:
                expected["TEAMWORK"] = Award(user.id, "TEAMWORK", teamwork[season][user.id], None)
            if season not in together:
                together[season] = all_together_days(db, season)
            if user.id in together[season]:
                day, game_id = together[season][user.id]
                expected["ALL_TOGETHER"] = Award(user.id, "ALL_TOGETHER", day, game_id)
            stored = stored_rows.filter(models.UserAchievement.user_id == user.id, models.UserAchievement.season == season).all()
            changes.extend(_diff(user, expected, stored, titles, {key for key in allowed if valid_from[key] <= season}))
        if lifetime_keys:  # whatever the seasons asked for: they belong to none
            stored = stored_rows.filter(models.UserAchievement.user_id == user.id, models.Achievement.key.in_(lifetime_keys)).all()
            expected, undecided = await _expected_lifetime(db, user)
            changes.extend(_diff(user, expected, stored, titles, lifetime_keys - undecided))
    return changes


def plan(
    db: Session,
    user_ids: list[int] | None = None,
    season_list: list[int] | None = None,
    achievement_keys: list[str] | None = None,
) -> list[Change]:
    """What a recalculation would change, for every player, season and achievement that is switched on or
    only the ones given. It changes nothing."""
    return asyncio.run(_plan(db, user_ids, None if season_list is None else set(season_list), achievement_keys))


async def recalculate_user(db: Session, user_id: int, season_list: list[int], notify: bool = False) -> list[Change]:
    """Work out again the achievements of one user in some seasons and apply it. It is what follows a session
    that was added, edited or deleted: what it earns is added and what it earned and no longer holds is revoked.
    Silent unless `notify`, which announces what was added (the same notice a timer gives); a revocation, a
    corrected date and the two that need several players at once are never announced. The caller is already in an
    event loop and holds the lock of the checks."""
    changes = await _plan(db, [user_id], set(season_list))
    apply(db, changes)
    if notify:
        user = db.get(models.User, user_id)
        for change in changes:
            if change.action != "add" or change.key in MULTIPLAYER_KEYS or user is None:
                continue
            try:
                await actions.achievements.announce_added(db, user, change.key, change.game_after)
            except Exception as e:  # a notice must not stop the rest
                logger.error(f"Error announcing {change.key} to {user.username}: {e}")
    return changes


def preview(
    db: Session,
    user_ids: list[int] | None = None,
    season_list: list[int] | None = None,
    achievement_keys: list[str] | None = None,
) -> dict:
    changes = plan(db, user_ids, season_list, achievement_keys)
    counts = {action: sum(1 for change in changes if change.action == action) for action in ("add", "date", "revoke")}
    wanted = {game for change in changes for game in (change.game_before, change.game_after) if game}
    names = dict(db.query(models.Game.id, models.Game.name).filter(models.Game.id.in_(list(wanted))).all()) if wanted else {}
    items = []
    for change in changes:
        item = change.as_dict()
        # the panel shows the name of the game, not its id
        item["game_before_name"] = names.get(change.game_before, change.game_before)
        item["game_after_name"] = names.get(change.game_after, change.game_after)
        items.append(item)
    return {"counts": counts, "changes": items}


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


def recalculate(
    user_ids: list[int] | None = None, season_list: list[int] | None = None, achievement_keys: list[str] | None = None
) -> None:
    """Background-task entrypoint of the admin panel: work everything out again and apply it, in silence.

    Under the lock of the other checks, with its own DB session, like the rest of the follow-ups."""
    from ..database.database import SessionLocal

    with actions._check_lock:
        try:
            with SessionLocal() as db:
                changes = plan(db, user_ids, season_list, achievement_keys)
                apply(db, changes)
            logger.info(f"Achievements recalculated: {len(changes)} changes")
        except Exception as e:
            logger.error("Error recalculating the achievements: " + str(e))
