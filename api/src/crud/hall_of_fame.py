"""The hall of fame: who won each closed season. Derived from the sessions, the library and the achievements when asked,
nothing is stored (so correcting a session or a date changes the past champions too).

A season has one champion per category: the player with the highest figure, all of them on a tie, none when nobody has
anything. Every player counts, active today or not (the emergency account never does). The running season is not
here: it is still being played."""
from sqlalchemy import select, union
from sqlalchemy.orm import Session

from ..database import models
from ..utils import seasons
from . import rankings


def closed_seasons(db: Session) -> list[int]:
    """The seasons before the running one in which something was played or added to a library, newest first."""
    played = select(models.GameTimer.season).where(models.GameTimer.is_active == False)  # noqa: E712
    added = select(models.UserGame.season)
    found = db.execute(union(played, added)).scalars().all()
    return sorted({season for season in found if season is not None and season < seasons.current()}, reverse=True)


def _rows(ranking) -> list[dict]:
    return [dict(getattr(row, "_mapping", row)) for row in ranking]


def champions(rows: list[dict], key: str) -> list[dict]:
    """The rows with the highest `key` (all of them on a tie), as {user_id, name, value}; none when it is 0."""
    top = max((row[key] for row in rows), default=0)
    if top <= 0:
        return []
    return [{"user_id": row["user_id"], "name": row["name"], "value": row[key]} for row in rows if row[key] == top]


def season_champions(db: Session, season: int) -> dict[str, list[dict]]:
    """The champions of each category of one season."""
    players = rankings.players_with_dates(db, None, season)  # the days played, shared by the days and the streak
    counts = rankings.library_counts(db, season)
    figures = {
        "hours": (rankings.user_hours_players(db, season=season), "played_time"),
        "days": (rankings.user_days_played(db, players=players), "played_days"),
        "games": (rankings.user_played_games(db, season=season), "played_games"),
        "completed": (rankings.user_completed_games(db, counts=counts), "completed_games"),
        "achievements": (rankings.user_ranking_achievements(db, season=season), "achievements"),
        "streak": (rankings.user_best_streak(db, players=players), "best_streak"),
    }
    return {category: champions(_rows(rows), key) for category, (rows, key) in figures.items()}


def hall_of_fame(db: Session) -> dict:
    """The champions of every closed season, newest first, and who has won most titles over all of them."""
    history = [{"season": season, "champions": season_champions(db, season)} for season in closed_seasons(db)]
    titles: dict[int, dict] = {}
    for entry in history:
        for winners in entry["champions"].values():
            for winner in winners:
                won = titles.setdefault(winner["user_id"], {"user_id": winner["user_id"], "name": winner["name"], "titles": 0})
                won["titles"] += 1
    ranking = sorted(titles.values(), key=lambda t: (-t["titles"], t["user_id"]))
    return {"seasons": history, "titles": ranking}
