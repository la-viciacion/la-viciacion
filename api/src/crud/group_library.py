"""The group's library as a whole: hidden gems, the graveyard, rarities, what nobody has touched and what the libraries
cover by genre and platform. Derived from the libraries, the sessions and the ratings when asked; nothing is stored.
Every player counts, active or not (never the emergency account), like the rankings and the game pages."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from ..utils.ttl_cache import TtlCache
from . import games, users

LIST_SIZE = 10  # items of each list
HIDDEN_MAX_PLAYERS = 2  # a hidden gem is had by this many players at most...
HIDDEN_MIN_SCORE = 80  # ...and rated this well (the mean of the ratings) at least
COVERAGE_SIZE = 10  # genres and platforms listed
_cache = TtlCache(120)  # the whole group's library changes slowly and costs a scan of every library: a couple of minutes old is fine


# ── the lists (pure, from the facts) ────────────────────────────
# facts: {"owners": {game: {users}}, "seconds": {game: total}, "scores": {game: [ratings]}, "abandoned_by": {game: {users}},
# "completed": {game: {users}}, "genres": {game: [genres]}, "platforms": {platform: {game: {users}}}}


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


def untouched(facts: dict) -> list[dict]:
    """The games somebody has and nobody has ever played, the most owned first."""
    found = [
        {"game_id": game, "players": len(owners)}
        for game, owners in facts["owners"].items() if not facts["seconds"].get(game)
    ]
    return sorted(found, key=lambda g: (-g["players"], g["game_id"]))


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
    meta = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_(list(owners) or [""]))}
    return {
        "owners": owners, "seconds": seconds, "scores": scores, "abandoned_by": abandoned_by, "completed": completed,
        "genres": {game_id: games.genre_list(game.genres) for game_id, game in meta.items()}, "platforms": platforms, "meta": meta,
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

    rare, dust = rarities(facts), untouched(facts)
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
        "untouched": {"total": len(dust), "items": [{**game(g["game_id"]), "players": g["players"]} for g in dust[:LIST_SIZE]]},
        "genres": by_genre(facts)[:COVERAGE_SIZE],
        "platforms": [{**row, "platform_name": platform_names.get(row["platform"], row["platform"])} for row in by_platform(facts)[:COVERAGE_SIZE]],
    }
