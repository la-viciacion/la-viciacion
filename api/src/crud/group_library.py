"""The group's library as a whole: hidden gems, the graveyard, rarities, what the group waits for, plays and finishes together,
its sagas and what the libraries cover by genre and platform. Derived from the libraries, the sessions and the ratings when asked; nothing is stored.
Every player counts, active or not (never the emergency account), like the rankings and the game pages."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from ..utils.ttl_cache import TtlCache
from . import games, users
from .wishlist import is_upcoming

LIST_SIZE = 10  # items of each list
HIDDEN_MAX_PLAYERS = 2  # a hidden gem is had by this many players at most...
HIDDEN_MIN_SCORE = 80  # ...and rated this well (the mean of the ratings) at least
MIN_PLAYERS = 2  # a game is listed as played or completed together from this many players
MIN_SAGA_GAMES = 2  # a saga has this many games in the libraries at least
COVERAGE_SIZE = 10  # genres and platforms listed
_cache = TtlCache(120)  # the whole group's library changes slowly and costs a scan of every library: a couple of minutes old is fine


# ── the lists (pure, from the facts) ────────────────────────────
# facts: {"owners": {game: {users}}, "seconds": {game: total}, "scores": {game: [ratings]}, "abandoned_by": {game: {users}},
# "completed": {game: {users}}, "genres": {game: [genres]}, "platforms": {platform: {game: {users}}},
# "wishes": {game: [active users who wish for it]}, "released": {game: date or None}, "played_by": {game: {season: {users}}},
# "seconds_by": {game: {user: seconds}}, "franchises": {game: [franchises]}}


def hidden_gems(facts: dict) -> list[dict]:
    """Games few players have that those who rated them like: at most HIDDEN_MAX_PLAYERS owners, at least one rating and
    a mean of HIDDEN_MIN_SCORE or more; the best rated first, then the fewest owners."""
    found = []
    for game, owners in facts["owners"].items():
        scores = facts["scores"].get(game, [])
        if scores and len(owners) <= HIDDEN_MAX_PLAYERS and sum(scores) / len(scores) >= HIDDEN_MIN_SCORE:
            found.append({"game_id": game, "players": len(owners), "score_mean": round(sum(scores) / len(scores), 1), "score_count": len(scores)})
    return sorted(found, key=lambda g: (-g["score_mean"], g["players"], g["game_id"]))


def graveyard(facts: dict) -> list[dict]:
    """The games players gave up and have not gone back to, the most abandoned first (then by the hours put into them)."""
    found = [
        {"game_id": game, "players": len(facts["owners"].get(game, ())), "abandoned_by": sorted(users_)}
        for game, users_ in facts["abandoned_by"].items() if users_
    ]
    return sorted(found, key=lambda g: (-len(g["abandoned_by"]), -facts["seconds"].get(g["game_id"], 0), g["game_id"]))


def rarities(facts: dict) -> list[dict]:
    """The games that exactly one player has, the most played first."""
    found = [
        {"game_id": game, "owner": next(iter(owners)), "seconds": facts["seconds"].get(game, 0)}
        for game, owners in facts["owners"].items() if len(owners) == 1
    ]
    return sorted(found, key=lambda g: (-g["seconds"], g["game_id"]))


def most_wanted(facts: dict) -> list[dict]:
    """The games the most active players wish for; on a tie the soonest release first (games without a date last)."""
    found = [{"game_id": game, "wanters": list(wanters)} for game, wanters in facts["wishes"].items() if wanters]

    def key(g):
        released = facts["released"].get(g["game_id"])
        return (-len(g["wanters"]), released is None, released or datetime.date.min, g["game_id"])

    return sorted(found, key=key)


def played_together(facts: dict) -> list[dict]:
    """The games MIN_PLAYERS players or more played in the same season (the one with the most of them), the most players
    first, then the hours put into the game."""
    found = []
    for game, per_season in facts["played_by"].items():
        count, season = max((len(users_), season) for season, users_ in per_season.items())
        if count >= MIN_PLAYERS:
            found.append({"game_id": game, "players": count, "season": season, "seconds": facts["seconds"].get(game, 0)})
    return sorted(found, key=lambda g: (-g["players"], -g["seconds"], g["game_id"]))


def finished_by_many(facts: dict) -> list[dict]:
    """The games MIN_PLAYERS players or more completed, with how many of the players who have it did and the mean time
    those who finished it put in (None when none has sessions); the most completions first, then the fewest owners."""
    found = []
    for game, done in facts["completed"].items():
        if len(done) < MIN_PLAYERS:
            continue
        times = [t for t in (facts["seconds_by"].get(game, {}).get(user) for user in done) if t]
        found.append({
            "game_id": game, "completed": len(done), "players": len(facts["owners"].get(game, done)),
            "mean_seconds": round(sum(times) / len(times)) if times else None,
        })
    return sorted(found, key=lambda g: (-g["completed"], g["players"], g["game_id"]))


def sagas(facts: dict) -> list[dict]:
    """The franchises with MIN_SAGA_GAMES games or more in the libraries: how many, the players who have any and their
    hours, the most games first."""
    found: dict[str, dict] = {}
    for game, owners in facts["owners"].items():
        for name in facts["franchises"].get(game, []):
            row = found.setdefault(name, {"saga": name, "games": 0, "players": set(), "seconds": 0})
            row["games"] += 1
            row["players"] |= owners
            row["seconds"] += facts["seconds"].get(game, 0)
    rows = [{**row, "players": len(row["players"])} for row in found.values() if row["games"] >= MIN_SAGA_GAMES]
    return sorted(rows, key=lambda r: (-r["games"], -r["seconds"], r["saga"]))


def by_genre(facts: dict) -> list[dict]:
    """For each genre: the games of the libraries that have it, the players who have one, the hours and the completions
    (a game of several genres counts in each), the most games first."""
    found: dict[str, dict] = {}
    for game, owners in facts["owners"].items():
        for genre in facts["genres"].get(game, []):
            row = found.setdefault(genre, {"genre": genre, "games": 0, "players": set(), "seconds": 0, "completed": 0})
            row["games"] += 1
            row["players"] |= owners
            row["seconds"] += facts["seconds"].get(game, 0)
            row["completed"] += len(facts["completed"].get(game, ()))
    rows = [{**row, "players": len(row["players"])} for row in found.values()]
    return sorted(rows, key=lambda r: (-r["games"], -r["seconds"], r["genre"]))


def by_platform(facts: dict) -> list[dict]:
    """For each platform: the games played or owned on it and the players, the most games first."""
    rows = [
        {"platform": platform, "games": len(per_game), "players": len({user for users_ in per_game.values() for user in users_})}
        for platform, per_game in facts["platforms"].items() if per_game
    ]
    return sorted(rows, key=lambda r: (-r["games"], -r["players"], str(r["platform"])))


# ── the facts (from the database) ───────────────────────────────


def _facts(db: Session) -> dict:
    players = {user_id for (user_id,) in db.query(models.User.id).filter(models.not_god())}
    owners: dict[str, set] = {}
    completed: dict[str, set] = {}
    platforms: dict[str, dict] = {}
    entries = db.query(
        models.UserGame.user_id, models.UserGame.game_id, models.UserGame.platform, models.UserGame.completed,
        models.UserGame.abandoned_at, models.UserGame.season,
    ).all()
    candidates: dict[tuple, list] = {}  # (user, game, season) -> the abandoned marks of its entries
    done_keys: set[tuple] = set()  # (user, game, season) completed on any platform
    for user_id, game_id, platform, done, abandoned_at, season in entries:
        if user_id not in players:
            continue
        owners.setdefault(game_id, set()).add(user_id)
        if done:
            completed.setdefault(game_id, set()).add(user_id)
            done_keys.add((user_id, game_id, season))
        elif abandoned_at is not None:
            candidates.setdefault((user_id, game_id, season), []).append(abandoned_at)
        if platform:
            platforms.setdefault(platform, {}).setdefault(game_id, set()).add(user_id)
    seconds = {
        game_id: int(total or 0)  # MariaDB returns SUM() as Decimal
        for game_id, total in db.query(models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds))
        .filter(models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.game_id)
    }
    scores: dict[str, list] = {}
    for user_id, game_id, value in db.query(models.GameScore.user_id, models.GameScore.game_id, models.GameScore.score):
        if user_id in players:
            scores.setdefault(game_id, []).append(value)
    # given up and not gone back to: no session after the mark (users.is_abandoned); a game completed that season, on any
    # platform, is never abandoned
    last = {
        (user_id, game_id, season): last_played
        for user_id, game_id, season, last_played in db.query(users._last_played_by_year())
    } if candidates else {}
    abandoned_by: dict[str, set] = {}
    for key, marks in candidates.items():
        played = last.get(key)
        if key not in done_keys and (played is None or played <= max(marks)):
            abandoned_by.setdefault(key[1], set()).add(key[0])
    wishes: dict[str, list] = {}  # active players only, like every "who wants it" of the app
    for game_id, user_id in (
        db.query(models.UserWishlist.game_id, models.UserWishlist.user_id)
        .join(models.User, models.User.id == models.UserWishlist.user_id)
        .filter(models.User.is_active == 1, models.not_god())
        .order_by(models.UserWishlist.added_at, models.User.id)
    ):
        wishes.setdefault(game_id, []).append(user_id)
    played_by: dict[str, dict] = {}
    seconds_by: dict[str, dict] = {}
    for game_id, user_id, season, total in (
        db.query(models.GameTimer.game_id, models.GameTimer.user_id, models.GameTimer.season, func.sum(models.GameTimer.duration_seconds))
        .filter(models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.game_id, models.GameTimer.user_id, models.GameTimer.season)
    ):
        if user_id in players:
            played_by.setdefault(game_id, {}).setdefault(season, set()).add(user_id)
            by_user = seconds_by.setdefault(game_id, {})
            by_user[user_id] = by_user.get(user_id, 0) + int(total or 0)
    meta = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_(list({*owners, *wishes} or [""])))}
    return {
        "owners": owners, "seconds": seconds, "scores": scores, "abandoned_by": abandoned_by, "completed": completed,
        "genres": {game_id: games.genre_list(game.genres) for game_id, game in meta.items()}, "platforms": platforms, "meta": meta,
        "wishes": wishes, "played_by": played_by, "seconds_by": seconds_by,
        "released": {game_id: game.release_date for game_id, game in meta.items()},
        # IGDB's franchises; a game that has none may still belong to a collection (a series)
        "franchises": {game_id: games.genre_list(game.franchises) or games.genre_list(game.collections) for game_id, game in meta.items()},
    }


def library(db: Session) -> dict:
    """The group's library: totals and the lists above (see the module's docstring). Kept for a couple of minutes."""
    return _cache.get("library", lambda: _library(db))


def _library(db: Session) -> dict:
    facts = _facts(db)
    meta = facts["meta"]
    names = {user_id: name or username for user_id, username, name in db.query(models.User.id, models.User.username, models.User.name)}
    platform_names = dict(db.query(models.PlatformTag.id, models.PlatformTag.name))

    def game(game_id: str) -> dict:
        found = meta[game_id]
        return {"game_id": game_id, "game_name": found.name, "image_url": found.image_url}

    rare, wanted, together, finished, series = rarities(facts), most_wanted(facts), played_together(facts), finished_by_many(facts), sagas(facts)
    today = datetime.date.today()
    return {
        "summary": {
            "games": len(facts["owners"]),
            "players": len({user for owners in facts["owners"].values() for user in owners}),
            "played_seconds": sum(facts["seconds"].get(game_id, 0) for game_id in facts["owners"]),
        },
        "hidden_gems": [{**game(g["game_id"]), **g} for g in hidden_gems(facts)[:LIST_SIZE]],
        "graveyard": [
            {**game(g["game_id"]), **{**g, "abandoned_by": [names[u] for u in g["abandoned_by"]]}} for g in graveyard(facts)[:LIST_SIZE]
        ],
        "rarities": {
            "total": len(rare),
            "items": [{**game(g["game_id"]), "owner": names[g["owner"]], "seconds": g["seconds"]} for g in rare[:LIST_SIZE]],
        },
        "wanted": {
            "total": len(wanted),
            "items": [
                {**game(g["game_id"]), "wanters": [names[u] for u in g["wanters"]], "release_date": meta[g["game_id"]].release_date,
                 "upcoming": is_upcoming(meta[g["game_id"]].release_date, today)}
                for g in wanted[:LIST_SIZE]
            ],
        },
        "together": {
            "total": len(together),
            "items": [{**game(g["game_id"]), "players": g["players"], "season": g["season"], "seconds": g["seconds"]} for g in together[:LIST_SIZE]],
        },
        "finished": {
            "total": len(finished),
            "items": [
                {**game(g["game_id"]), "completed": g["completed"], "players": g["players"], "mean_seconds": g["mean_seconds"]}
                for g in finished[:LIST_SIZE]
            ],
        },
        "sagas": {"total": len(series), "items": series[:LIST_SIZE]},
        "genres": by_genre(facts)[:COVERAGE_SIZE],
        "platforms": [{**row, "platform_name": platform_names.get(row["platform"], row["platform"])} for row in by_platform(facts)[:COVERAGE_SIZE]],
    }
