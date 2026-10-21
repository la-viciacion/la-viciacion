"""What the chat can look up: read-only views over the same CRUD functions the app's pages use.

Rules for every tool: it answers from what the app derives when asked (nothing is stored for the chat), it
returns small plain dicts (never rows, nor the library of another player), it caps the number of items, and it
sees the group as the logged-in user does (`deps.user`). There is no tool that writes. Tools are `async` with a
blocking body on purpose: the agent runs them one after another on its own thread, so the one DB session is
never used by two at once."""
import datetime
import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic_ai import ModelRetry, RunContext
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..crud import activity, affinity, game_overview, games, group, rankings, time_entries, wishlist
from ..database import models
from ..utils import seasons
from . import help as app_help_topics
from . import limits

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


# The genres and tags of the catalog come from RAWG, in English: what a player asks for in Spanish, as RAWG calls it
SEARCH_TERMS = {
    "terror": "horror", "miedo": "horror", "rol": "rpg", "plataformas": "platformer", "plataforma": "platformer",
    "cooperativo": "co-op", "cooperativos": "co-op", "cooperacion": "co-op", "mundo abierto": "open world",
    "carreras": "racing", "conduccion": "racing", "estrategia": "strategy", "puzle": "puzzle", "puzles": "puzzle",
    "rompecabezas": "puzzle", "lucha": "fighting", "peleas": "fighting", "disparos": "shooter", "tiros": "shooter",
    "deportes": "sports", "deporte": "sports", "simulacion": "simulation", "aventura": "adventure", "aventuras": "adventure",
    "accion": "action", "sigilo": "stealth", "supervivencia": "survival", "un jugador": "singleplayer",
    "multijugador": "multiplayer", "indie": "indie", "casual": "casual", "arcade": "arcade", "musica": "music",
    "ritmo": "music", "familiar": "family", "educativo": "educational", "fantasia": "fantasy", "ciencia ficcion": "sci-fi",
}


def search_terms(query: str) -> list[str]:
    """What to look for: the words as typed and, when it is one the catalog calls otherwise, its English name."""
    typed = query.strip()
    plain = "".join(c for c in unicodedata.normalize("NFD", typed.lower()) if not unicodedata.combining(c))
    return [typed] + ([SEARCH_TERMS[plain]] if plain in SEARCH_TERMS else [])


async def search_games(ctx: RunContext[ChatDeps], query: str) -> dict:
    """Looks for games of the group's catalog by a part of the name, a genre or a tag ("terror", "rpg", "zelda"; the
    genres and tags are in English in the catalog, and common Spanish words are translated). Returns up to 10 with their
    genres, release date and average time to finish (hours)."""
    conditions = [
        column.like(f"%{term}%") for term in search_terms(query) for column in (models.Game.name, models.Game.genres, models.Game.tags)
    ]
    found = ctx.deps.db.query(models.Game).filter(or_(*conditions)).order_by(models.Game.name).limit(MAX_ITEMS).all()
    result: dict = {
        "games": [
            {
                "name": g.name,
                "genres": games.genre_list(g.genres),
                "release_date": _day(g.release_date),
                "average_hours_to_finish": hours(g.avg_time) if g.avg_time else None,
            }
            for g in found
        ]
    }
    if not found:
        result["note"] = "No hay juegos que encajen en el catálogo. No sigas buscando: dilo."
    return result


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


ActivityKind = Literal["played", "started", "completed", "rated", "achievement"]
FEED_WINDOW = 50  # events looked at when one kind is asked for: the latest of that kind may be further back


async def recent_activity(ctx: RunContext[ChatDeps], limit: int = 10, kind: ActivityKind | None = None) -> list[dict]:
    """The latest things that happened in the group: sessions played, games started or completed, ratings and
    achievements (a hidden achievement is reported without who nor which). `kind` keeps only one of those."""
    limit = max(1, min(limit, MAX_ITEMS))
    events = activity.feed(ctx.deps.db, limit=FEED_WINDOW if kind else limit)["items"]
    events = [e for e in events if kind is None or e["type"] == kind][:limit]
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


async def affinity_with_players(ctx: RunContext[ChatDeps]) -> list[dict]:
    """How alike the user's taste is to each other player's (percent, games and ratings in common), the most alike
    first; no percent when there is too little in common to say."""
    names = {u.id: u.name or u.username for u in ctx.deps.db.query(models.User).filter(models.not_god())}
    return [
        {"name": names[r["user_id"]], "percent": r["percent"], "shared_games": r["shared_games"], "shared_rated": r["shared_rated"]}
        for r in affinity.with_everyone(ctx.deps.db, ctx.deps.user.id)
    ]


async def chat_limits(ctx: RunContext[ChatDeps]) -> dict:
    """The limits of this chat and how much of them is used: the questions each player and the whole group may ask per
    minute, hour and day (the day is the last 24 hours) with how many are used and left now, this question included
    (`limit` null: no limit), and what one question may cost. Use it for "how many questions do I have left" or "what limits
    does the chat have"."""
    return {
        "questions": limits.usage_of(ctx.deps.user.id),
        "per_question": {
            "max_characters": limits.MAX_QUESTION,
            "conversation_messages_the_model_sees": limits.MAX_HISTORY,
            "model_requests": limits.LIMITS.request_limit,
            "tool_calls": limits.LIMITS.tool_calls_limit,
        },
        "note": "El administrador ajusta los límites de preguntas desde el panel; reiniciar el servidor pone los contadores a cero.",
    }


async def app_help(ctx: RunContext[ChatDeps], topic: str = "") -> dict:
    """How the app works and where things are (not the group's data): logging in and installing it, timers and sessions,
    completing, rating and abandoning games, seasons, days and streaks, achievements, the profile and settings, the
    group's pages, the wishlist, recommendations, challenges, the monthly and yearly summary, notifications and Telegram,
    who sees what and this chat. Pass a few words of the topic ("temporadas", "sesión manual", "notificaciones"); empty
    gives the list of topics. Answer only from what it returns: if it does not say it, say you do not know."""
    found = app_help_topics.find(topic) if topic.strip() else []
    if not found:
        return {"topics": app_help_topics.index(), "note": "Pide uno de estos temas con unas pocas palabras." if topic.strip() else "Temas disponibles."}
    return {"topics": [{"topic": t.id, "title": t.title, "text": t.text, "guide_page": f"docs/guia-usuario/{t.source}"} for t in found]}


async def achievements(ctx: RunContext[ChatDeps], query: str = "", only: Literal["mine", "missing"] | None = None) -> dict:
    """The achievements of the running season and the lifetime ones: for each its title, whether the user has it, how many
    players do and, for the user's own, what it is about. What the user does not have comes with no description, and the
    hidden ones only as a count: finding out what they are about is part of the game, so never say how to get one the
    user does not have. `query` filters by title or description, `only` keeps the user's own or the ones still missing.
    Up to 10 are listed; progress (e.g. "35 / 100") is given for the ones that add up."""
    catalog = group.achievements_catalog(ctx.deps.db, ctx.deps.user.id)
    words = (query or "").lower().split()
    shown = [a for a in catalog if not a["hidden"]]
    if only == "mine":
        shown = [a for a in shown if a["unlocked_by_me"]]
    elif only == "missing":
        shown = [a for a in shown if not a["unlocked_by_me"]]
    if words:
        shown = [a for a in shown if all(w in f"{a['title']} {a['description'] or ''}".lower() for w in words)]
    return {
        "total_visible": len([a for a in catalog if not a["hidden"]]),
        "mine": len([a for a in catalog if a["unlocked_by_me"]]),
        "hidden_ones_not_unlocked": len([a for a in catalog if a["hidden"]]),
        "achievements": [
            {
                "title": a["title"],
                "mine": a["unlocked_by_me"],
                "players_who_have_it": a["unlocked_by"],
                "kind": "lifetime" if a["lifetime"] else "season",
                "special_level": a["special"] or None,
                **({"description": a["description"]} if a["description"] else {}),
                **({"progress": a["progress"]} if a["progress"] else {}),
            }
            for a in shown[:MAX_ITEMS]
        ],
        "more": max(0, len(shown) - MAX_ITEMS),
    }


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


TOOLS = [
    search_games, game_info, players, player_profile, ranking, most_played_games, recent_activity, affinity_with_players,
    my_wishlist, achievements, chat_limits, app_help,
]
