"""Two libraries side by side: the games both players have, the ones only the viewer has and the ones only the other
has. Derived from the libraries, the sessions and the ratings when asked; nothing is stored. It shows what the game
page already shows (who has each game, with their hours and rating), grouped by pair of players."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models
from . import affinity


def _library(db: Session, user_id: int) -> dict[str, dict]:
    """{game id: {"seconds", "completed", "score"}} of the games in the player's library, every season."""
    owned = {game_id for (game_id,) in db.query(models.UserGame.game_id).filter(models.UserGame.user_id == user_id)}
    completed = {
        game_id for (game_id,) in db.query(models.UserGame.game_id).filter(models.UserGame.user_id == user_id, models.UserGame.completed == 1)
    }
    seconds = {
        game_id: int(total or 0)  # MariaDB returns SUM() as Decimal
        for game_id, total in db.query(models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds))
        .filter(models.GameTimer.user_id == user_id, models.GameTimer.is_active == False)  # noqa: E712
        .group_by(models.GameTimer.game_id)
    }
    scores = dict(db.query(models.GameScore.game_id, models.GameScore.score).filter(models.GameScore.user_id == user_id))
    return {
        game_id: {"seconds": seconds.get(game_id, 0), "completed": game_id in completed, "score": scores.get(game_id)}
        for game_id in owned
    }


def split(mine: dict, theirs: dict) -> tuple[list[str], list[str], list[str]]:
    """(shared, only mine, only theirs) game ids, each from the most played to the least (pure): the shared by what the
    two played together, the others by what their owner played; ties by id."""
    def order(ids, key):
        return sorted(ids, key=lambda game_id: (-key(game_id), game_id))

    shared = order(mine.keys() & theirs.keys(), lambda g: mine[g]["seconds"] + theirs[g]["seconds"])
    only_mine = order(mine.keys() - theirs.keys(), lambda g: mine[g]["seconds"])
    only_theirs = order(theirs.keys() - mine.keys(), lambda g: theirs[g]["seconds"])
    return shared, only_mine, only_theirs


def compare(db: Session, viewer_id: int, player: models.User) -> dict:
    """The viewer's library and another player's, side by side, with the affinity of the two."""
    mine, theirs = _library(db, viewer_id), _library(db, player.id)
    shared, only_mine, only_theirs = split(mine, theirs)
    found = {
        game.id: game for game in db.query(models.Game).filter(models.Game.id.in_(list(mine.keys() | theirs.keys()) or [""]))
    }

    def row(game_id: str) -> dict:
        game = found[game_id]
        return {"game_id": game_id, "game_name": game.name, "image_url": game.image_url, "mine": mine.get(game_id), "theirs": theirs.get(game_id)}

    return {
        "player": {"id": player.id, "name": player.name or player.username},
        "affinity": affinity.between(db, viewer_id, player.id),
        "counts": {"shared": len(shared), "only_mine": len(only_mine), "only_theirs": len(only_theirs)},
        "shared": [row(game_id) for game_id in shared],
        "only_mine": [row(game_id) for game_id in only_mine],
        "only_theirs": [row(game_id) for game_id in only_theirs],
    }
