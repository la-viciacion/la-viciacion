"""What the chat can look up: read-only views over the same CRUD functions the app's pages use.

Rules for every tool: it answers from what the app derives when asked (nothing is stored for the chat), it
returns small plain dicts (never rows, nor the library of another player), it caps the number of items, and it
sees the group as the logged-in user does (`deps.user`). There is no tool that writes. Tools are `async` with a
blocking body on purpose: the agent runs them one after another on its own thread, so the one DB session is
never used by two at once."""
import datetime
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import ModelRetry, RunContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..crud import activity, game_overview, games, group, rankings, time_entries, wishlist
from ..database import models
from ..utils import seasons

MAX_ITEMS = 10  # the most items any tool returns: the model gets what fits in a short answer


@dataclass
class ChatDeps:
    db: Session
    user: models.User


def hours(seconds) -> float:
    """Seconds as hours with one decimal: the model reads them better than seconds and does not have to convert."""
    return round(int(seconds or 0) / 3600, 1)


def _season(season: int | None) -> int:
    """`None` is the running season, 0 all of them; a future one is refused so the model corrects itself."""
    if season is not None and season > seasons.current():
        raise ModelRetry(f"La temporada {season} todavía no existe; la actual es {seasons.current()}")
    return seasons.or_current(season)


def _day(value) -> str | None:
    return value.isoformat() if isinstance(value, (datetime.date, datetime.datetime)) else None


def find_player(db: Session, text: str) -> models.User:
    """The player named `text` (name or username, whatever the case); ModelRetry with the options if none or several."""
    wanted = text.strip().lower()
    users = db.query(models.User).filter(models.not_god()).all()
    exact = [u for u in users if wanted in {(u.name or "").lower(), u.username.lower()}]
    found = exact or [u for u in users if wanted and (wanted in (u.name or "").lower() or wanted in u.username.lower())]
    if len(found) == 1:
        return found[0]
    names = ", ".join(sorted(u.name or u.username for u in (found or users))[:20])
    raise ModelRetry(f"No sé a qué jugador te refieres con '{text}'. Opciones: {names}")


def find_game(db: Session, text: str) -> models.Game:
    """The game named `text` (the exact name first, then a part of it); ModelRetry with the candidates if none or several."""
    exact = db.query(models.Game).filter(models.Game.name == text.strip()).first()
    if exact:
        return exact
    found = games.get_game_by_name(db, text.strip()).limit(6).all()
    if len(found) == 1:
        return found[0]
    if not found:
        raise ModelRetry(f"No hay ningún juego llamado '{text}' en la base de datos del grupo")
    raise ModelRetry("Hay varios juegos que encajan, usa el nombre exacto o pregunta cuál: " + "; ".join(g.name for g in found))


async def search_games(ctx: RunContext[ChatDeps], query: str) -> list[dict]:
    """Looks for games of the group's catalog by a part of the name, a genre or a tag ("terror", "rpg", "zelda").
    Returns up to 10 with their genres, release date and average time to finish (hours)."""
    like = f"%{query.strip()}%"
    found = (
        ctx.deps.db.query(models.Game)
        .filter(or_(models.Game.name.like(like), models.Game.genres.like(like), models.Game.tags.like(like)))
        .order_by(models.Game.name)
        .limit(MAX_ITEMS)
        .all()
    )
    return [
        {
            "name": g.name,
            "genres": games.genre_list(g.genres),
            "release_date": _day(g.release_date),
            "average_hours_to_finish": hours(g.avg_time) if g.avg_time else None,
        }
        for g in found
    ]


async def game_info(ctx: RunContext[ChatDeps], game: str) -> dict:
    """Everything the group has done with one game (by name): its data, how many have it, total hours, how many
    completed it, the average rating and, for each player, their hours, completion and rating."""
    found = find_game(ctx.deps.db, game)
    data = game_overview.overview(ctx.deps.db, found.id, ctx.deps.user.id)
    info, summary = data["game"], data["summary"]
    return {
        "name": info["name"],
        "genres": info["genres"],
        "tags": info["tags"][:8],
        "developer": info["dev"],
        "release_date": _day(info["release_date"]),
        "average_hours_to_finish": hours(info["avg_time"]) if info["avg_time"] else None,
        "players_count": summary["players"],
        "total_hours": hours(summary["played_seconds"]),
        "completed_by": summary["completed_by"],
        "rating_average_out_of_100": summary["score_mean"],
        "players": [
            {
                "name": p["name"],
                "hours": hours(p["played_seconds"]),
                "sessions": p["sessions"],
                "completed": p["completed"],
                "rating_out_of_100": p["score"],
                "playing_now": p["playing"],
                "last_played": _day(p["last_played"]),
            }
            for p in data["players"][:MAX_ITEMS]
        ],
    }


async def players(ctx: RunContext[ChatDeps]) -> list[dict]:
    """The players of the group with their totals over every season (hours, games, completed games, achievements),
    when they played last and what they are playing right now."""
    return [
        {
            "name": p["name"],
            "active": p["is_active"],
            "hours": hours(p["played_seconds"]),
            "games": p["games"],
            "completed": p["completed"],
            "achievements": p["achievements"],
            "last_played": _day(p["last_played"]),
            "playing_now": p["playing"]["game_name"] if p["playing"] else None,
        }
        for p in group.players(ctx.deps.db, ctx.deps.user.id)
    ]


async def player_profile(ctx: RunContext[ChatDeps], player: str, season: int | None = None) -> dict:
    """The public figures of one player (by name) in a season (default: the running one; 0 for all of them):
    hours, days played, streaks, games, completed games, top games with their rating, recent achievements and how
    alike their taste is to the user's."""
    target = find_player(ctx.deps.db, player)
    data = group.player_profile(ctx.deps.db, ctx.deps.user.id, target.id, _season(season))
    stats = data["stats"]
    return {
        "name": data["user"]["name"],
        "season": data["season"],
        "hours": hours(stats["played_time"]),
        "days_played": stats["played_days"],
        "games_played": stats["played_games"],
        "completed_games": stats["completed_games"],
        "current_streak_days": stats["current_streak"],
        "best_streak_days": stats["best_streak"],
        "achievements": stats["achievements"],
        "top_games": [
            {"name": g["game_name"], "hours": hours(g["played_time"]), "rating_out_of_100": g["score"]}
            for g in data["top_games"]
        ],
        "latest_achievements": [{"title": a["title"], "date": _day(a["date"])} for a in data["achievements"]],
        "playing_now": data["playing"]["game_name"] if data["playing"] else None,
        "affinity_with_the_user": data["affinity"],
    }


Metric = Literal[
    "hours", "days_played", "best_streak", "current_streak", "completed_games", "played_games", "achievements", "completion_ratio"
]


async def ranking(ctx: RunContext[ChatDeps], metric: Metric, season: int | None = None) -> list[dict]:
    """The group's ranking by a metric in a season (default: the running one; 0 for all of them, only for hours):
    hours, days_played, best_streak, current_streak, completed_games, played_games, achievements or
    completion_ratio. Top 10, the best first. Streaks are always those of today."""
    db = ctx.deps.db
    value = _season(season)
    if value == seasons.ALL and metric != "hours":
        raise ModelRetry("Solo el ranking de horas se puede pedir para todas las temporadas a la vez")
    if metric == "hours":
        rows = time_entries.players_played_time(db, season=value)
        return [{"name": r["name"], "hours": hours(r["played_time"])} for r in rows[:MAX_ITEMS]]
    if metric == "days_played":
        return [{"name": r["name"], "days": r["played_days"]} for r in rankings.user_days_played(db, MAX_ITEMS)]
    if metric == "best_streak":
        return [{"name": r["name"], "days": r["best_streak"]} for r in rankings.user_best_streak(db, MAX_ITEMS)]
    if metric == "current_streak":
        return [{"name": r["name"], "days": r["current_streak"]} for r in rankings.user_current_streak(db, MAX_ITEMS)]
    if metric == "achievements":
        return [{"name": r.name, "achievements": r.achievements} for r in rankings.user_ranking_achievements(db, MAX_ITEMS, season=value)]
    if metric == "played_games":
        return [{"name": r.name, "games": r.played_games} for r in rankings.user_played_games(db, MAX_ITEMS, season=value)]
    if metric == "completion_ratio":
        return [{"name": r["name"], "ratio": r["ratio"]} for r in rankings.user_ratio(db, season=value)[:MAX_ITEMS]]
    return [{"name": r["name"], "games": r["completed_games"]} for r in rankings.user_completed_games(db, season=value)[:MAX_ITEMS]]


async def most_played_games(ctx: RunContext[ChatDeps], season: int | None = None) -> list[dict]:
    """The games the group has played the most hours in a season (default: the running one; 0 for all). Top 10."""
    rows = time_entries.games_played_time(ctx.deps.db, season=_season(season), limit=MAX_ITEMS)
    return [{"name": r["name"], "hours": hours(r["played_time"])} for r in rows]


async def recent_activity(ctx: RunContext[ChatDeps], limit: int = 10) -> list[dict]:
    """The latest things that happened in the group: sessions played, games started or completed, ratings and
    achievements (a hidden achievement is reported without who nor which)."""
    events = activity.feed(ctx.deps.db, limit=max(1, min(limit, MAX_ITEMS)))["items"]
    return [
        {
            "type": e["type"],
            "player": e["name"],
            "game": e["game_name"],
            "day": _day(e["day"]),
            **({"hours": hours(e["seconds"])} if "seconds" in e else {}),
            **({"achievement": e["title"]} if e.get("title") else {}),
            **({"rating_out_of_100": e["score"]} if e.get("score") is not None else {}),
        }
        for e in events
    ]


async def my_wishlist(ctx: RunContext[ChatDeps]) -> dict:
    """The user's own wishlist: upcoming games (with the days left) and released ones they still want, and who else wants them."""
    data = wishlist.wishlist(ctx.deps.db, ctx.deps.user.id, datetime.date.today())

    def item(game):
        return {
            "name": game["name"],
            "release_date": _day(game["release_date"]),
            "days_until_release": game["days_until"],
            "also_wanted_by": [w["name"] for w in game["wanted_by"]],
        }

    return {
        "upcoming": [item(g) for g in data["upcoming"][:MAX_ITEMS]],
        "released": [item(g) for g in data["wanted"][:MAX_ITEMS]],
    }


TOOLS = [search_games, game_info, players, player_profile, ranking, most_played_games, recent_activity, my_wishlist]
