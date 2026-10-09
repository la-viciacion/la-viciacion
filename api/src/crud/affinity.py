"""How alike the taste of two players is, derived when asked from their libraries, ratings and sessions (every
season); nothing is stored."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import games

# What each part weighs. A part that cannot be worked out (no game rated by both, no time played) leaves the
# total, and the others weigh what is left.
WEIGHTS = {"shared": 0.5, "ratings": 0.3, "genres": 0.2}
# Below this many games in both libraries there is not enough to say anything
MIN_SHARED_GAMES = 3
MAX_SCORE_GAP = 99  # ratings go from 1 to 100


def _shared_part(mine: set, theirs: set) -> float:
    """Games in both libraries over games in either (0 to 1)."""
    return len(mine & theirs) / len(mine | theirs)


def _ratings_part(mine: dict, theirs: dict) -> float | None:
    """How close the ratings are on the games both rated (1 for the same, 0 for 1 against 100); None if none."""
    common = mine.keys() & theirs.keys()
    if not common:
        return None
    return 1 - sum(abs(mine[game] - theirs[game]) for game in common) / len(common) / MAX_SCORE_GAP


def _genres_part(mine: dict, theirs: dict) -> float | None:
    """How much of the time played goes to the same genres: the overlap of the two shares of time (0 to 1)."""
    total_mine, total_theirs = sum(mine.values()), sum(theirs.values())
    if not total_mine or not total_theirs:
        return None
    return sum(min(mine[genre] / total_mine, theirs[genre] / total_theirs) for genre in mine.keys() & theirs.keys())


def score(mine: dict, theirs: dict) -> dict:
    """The affinity of two players from {"games": set, "scores": {game: 1-100}, "genre_time": {genre: seconds}} each.

    `percent` is None when they share fewer than MIN_SHARED_GAMES games."""
    shared = len(mine["games"] & theirs["games"])
    rated = len(mine["scores"].keys() & theirs["scores"].keys())
    result = {"percent": None, "shared_games": shared, "shared_rated": rated}
    if shared < MIN_SHARED_GAMES:
        return result
    parts = {
        "shared": _shared_part(mine["games"], theirs["games"]),
        "ratings": _ratings_part(mine["scores"], theirs["scores"]),
        "genres": _genres_part(mine["genre_time"], theirs["genre_time"]),
    }
    used = {name: value for name, value in parts.items() if value is not None}
    result["percent"] = round(100 * sum(WEIGHTS[name] * value for name, value in used.items()) / sum(WEIGHTS[name] for name in used))
    return result


def _tastes(db: Session, user_ids: list[int]) -> dict[int, dict]:
    """The library, the ratings and the time played per genre of each player."""
    tastes = {user_id: {"games": set(), "scores": {}, "genre_time": {}} for user_id in user_ids}
    for user_id, game_id in db.query(models.UserGame.user_id, models.UserGame.game_id).filter(models.UserGame.user_id.in_(user_ids)):
        tastes[user_id]["games"].add(game_id)
    for user_id, game_id, value in db.query(models.GameScore.user_id, models.GameScore.game_id, models.GameScore.score).filter(
        models.GameScore.user_id.in_(user_ids)
    ):
        tastes[user_id]["scores"][game_id] = value
    played = (
        db.query(models.GameTimer.user_id, models.Game.genres, func.sum(models.GameTimer.duration_seconds))
        .join(models.Game, models.Game.id == models.GameTimer.game_id)
        .filter(models.GameTimer.user_id.in_(user_ids), models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.user_id, models.Game.genres)
    )
    for user_id, genres, seconds in played:
        for genre in games.genre_list(genres):
            by_genre = tastes[user_id]["genre_time"]
            by_genre[genre] = by_genre.get(genre, 0) + int(seconds or 0)  # MariaDB returns SUM() as Decimal
    return tastes


def between(db: Session, viewer_id: int, player_id: int) -> dict:
    """The affinity of the viewer with another player (see `score`)."""
    tastes = _tastes(db, [viewer_id, player_id])
    return score(tastes[viewer_id], tastes[player_id])
