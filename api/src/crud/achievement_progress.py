"""How far a player is from the achievements that add something up (hours, days, games, completions, a streak):
`progress` of the catalog of the Logros page. Derived when asked from the very data the checks read, so a bar and
the unlock agree; nothing is stored.

Only the cumulative families have one. "Hours in a single day" or "Del tirón" are about one moment, not a total,
so they have no bar, and secret achievements never do (the catalog hides them altogether). A season achievement
counts the running season; a lifetime one the whole history from the season it starts to count in (`since`).
The streak is the current run: how far the player is from the next day of it, not their best one."""
import datetime
from typing import Callable

from sqlalchemy.orm import Session

from ..utils import seasons, streaks
from . import time_entries, users  # before `achievements`: they import each other, and this order is the one that works
from . import achievements as checks

# metric -> [(achievement, needed)] per season, [(achievement, needed)] of the lifetime ones
FAMILIES = {
    "hours": (checks.TOTAL_HOURS, checks.LIFETIME_TOTAL_HOURS),
    "days": (checks.TOTAL_DAYS, checks.LIFETIME_TOTAL_DAYS),
    "games": (checks.PLAYED_GAMES, checks.LIFETIME_PLAYED_GAMES),
    "completed": (checks.COMPLETED_GAMES, checks.LIFETIME_COMPLETED_GAMES),
    "game_hours": (checks.HOURS_IN_A_GAME, checks.LIFETIME_HOURS_IN_A_GAME),
    "streak": (checks.STREAKS, ()),
}

# key -> (metric, needed)
TARGETS = {
    ach.name: (metric, needed)
    for metric, (season_table, lifetime_table) in FAMILIES.items()
    for ach, needed in (*season_table, *lifetime_table)
}


def target_of(key: str) -> tuple[str, int] | None:
    """(metric, needed) of an achievement that has a bar, None for the ones that do not."""
    return TARGETS.get(key)


def bar(current: float, needed: int) -> dict:
    """What the page draws: only how full the bar is, a whole percent. Neither the goal, the count nor its unit
    are sent on purpose: a locked achievement must not give away what it counts or where the limit is. A little
    progress still shows (never 0 once something is done) and a bar is only full when the goal is reached."""
    if current <= 0:
        return {"percent": 0}
    percent = int(min(current, needed) / needed * 100)
    return {"percent": max(1, min(100, percent))}


class Metrics:
    """The totals of one player over one scope (a season, or the whole history from `since`), each one worked out
    the first time it is asked for."""

    def __init__(self, db: Session, user_id: int, season: int, since: int | None, today: datetime.date):
        self.db, self.user_id, self.season, self.since, self.today = db, user_id, season, since, today
        self._cache: dict[str, float] = {}
        self._days: list[datetime.date] | None = None

    def _played_days(self) -> list[datetime.date]:
        if self._days is None:
            self._days = time_entries.get_played_days(self.db, self.user_id, self.season, self.since)
        return self._days

    def _hours(self) -> float:
        rows = time_entries.get_played_time_by_day(self.db, self.user_id, self.season, self.since)
        return sum(int(seconds or 0) for _, seconds in rows) / 3600  # MariaDB returns SUM() as Decimal

    def _game_hours(self) -> float:
        per_game: dict[str, int] = {}
        for _, game_id, seconds in time_entries.get_played_time_by_game_and_day(self.db, self.user_id, self.season, self.since):
            if game_id is not None:
                per_game[game_id] = per_game.get(game_id, 0) + int(seconds or 0)
        return max(per_game.values(), default=0) / 3600

    def _streak(self) -> int:
        return streaks.streak_summary(self._played_days(), self.today, self.season)[2]

    def get(self, metric: str) -> float:
        if metric not in self._cache:
            compute: dict[str, Callable[[], float]] = {
                "hours": self._hours,
                "days": lambda: len(self._played_days()),
                "games": lambda: len(users.played_game_dates(self.db, self.user_id, self.season, self.since)),
                "completed": lambda: len(users.completed_game_dates(self.db, self.user_id, self.season, self.since)),
                "game_hours": self._game_hours,
                "streak": self._streak,
            }
            self._cache[metric] = compute[metric]()
        return self._cache[metric]


class Progress:
    """The bars of one player: one `Metrics` per scope, made when an achievement of it is asked for."""

    def __init__(self, db: Session, user_id: int, today: datetime.date | None = None):
        self.db, self.user_id = db, user_id
        self.today = today or datetime.date.today()
        self._scopes: dict[tuple[int, int | None], Metrics] = {}

    def of(self, key: str, valid_from_season: int, lifetime: bool) -> dict | None:
        """The bar of an achievement for this player, None if it has none."""
        target = target_of(key)
        if target is None:
            return None
        metric, needed = target
        scope = (seasons.ALL, valid_from_season or None) if lifetime else (seasons.current(), None)
        if scope not in self._scopes:
            self._scopes[scope] = Metrics(self.db, self.user_id, scope[0], scope[1], self.today)
        return bar(self._scopes[scope].get(metric), needed)
