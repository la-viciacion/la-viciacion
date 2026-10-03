"""A player's rating of a game: 1-100, one per user and game (any season, any platform)."""
from sqlalchemy.orm import Session

from ..database import models

SCORE_MIN = 1
SCORE_MAX = 100


def user_scores(db: Session, user_id: int) -> dict[str, int]:
    """game_id -> rating, for every game the user rated."""
    rows = db.query(models.GameScore.game_id, models.GameScore.score).filter_by(user_id=user_id).all()
    return {game_id: score for game_id, score in rows}


def set_score(db: Session, user_id: int, game_id: str, score: int) -> None:
    """Rate a game or change the rating. Not committed."""
    row = db.query(models.GameScore).filter_by(user_id=user_id, game_id=game_id).first()
    if row is None:
        db.add(models.GameScore(user_id=user_id, game_id=game_id, score=score))
    else:
        row.score = score


def clear_score(db: Session, user_id: int, game_id: str) -> None:
    """Remove the rating (nothing happens if there is none). Not committed."""
    db.query(models.GameScore).filter_by(user_id=user_id, game_id=game_id).delete()
