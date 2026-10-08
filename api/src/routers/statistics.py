from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Row
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import rankings, users
from ..database import models, schemas
from ..utils import actions as actions
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

router = APIRouter(
    prefix="/statistics",
    tags=["Statistics"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


def plain(data):
    """Query rows as JSON-friendly dicts (FastAPI cannot serialize SQLAlchemy `Row`s)."""
    if isinstance(data, Row):
        return dict(data._mapping)
    if isinstance(data, (list, tuple)):
        return [plain(item) for item in data]
    return data


class _SharedRankingData:
    """What several rankings need, computed the first time and reused within one request."""

    def __init__(self, db: Session, is_active: bool | None = None):
        self._db = db
        self._is_active = is_active
        self._players = None
        self._counts = None

    @property
    def players(self):  # days played by every player: days, best and current streak
        if self._players is None:
            self._players = rankings.players_with_dates(self._db, self._is_active)
        return self._players

    @property
    def counts(self):  # library entries and completions per player: completed games, ratio
        if self._counts is None:
            self._counts = rankings.library_counts(self._db, is_active=self._is_active)
        return self._counts


class RankingStatisticsTypes(str, Enum):
    user_hours = "user_hours"
    user_days = "user_days"
    user_played_games = "user_played_games"
    user_completed_games = "user_completed_games"
    achievements = "achievements"
    user_ratio = "user_ratio"
    user_current_streak = "user_current_streak"
    user_best_streak = "user_best_streak"
    games_most_played = "games_most_played"
    platform_played = "platform_played"
    debt = "debt"
    games_last_played = "games_last_played"


@router.get(
    "/rankings",
    response_description="Return a list of rankings",
)
def get_ranking_statistics(
    ranking: str = None,
    only_active: bool = False,
    db: Session = Depends(get_db),
):
    """
    Get general rankings. To retrieve only specific rankings, add 'ranking' param with desired rankings, separated by comma (,).
    With `only_active=true` the inactive users are left out (the Telegram bot asks for it; the app counts everybody).

    Allowed values: 'user_hours', 'user_days', 'user_played_games',
    'user_completed_games', 'achievements', 'user_ratio', 'user_current_streak',
    'user_best_streak', 'games_most_played', 'platform_played', 'debt', 'games_last_played'
    """
    if ranking is not None:
        rankings_list = ranking.split(",")
    else:
        rankings_list = [elem.value for elem in RankingStatisticsTypes]
    is_active = True if only_active else None
    shared = _SharedRankingData(db, is_active)
    response = []
    for ranking_type in rankings_list:
        content = {}
        if ranking_type == RankingStatisticsTypes.user_hours:
            data = rankings.user_hours_players(db, is_active=is_active)
        elif ranking_type == RankingStatisticsTypes.user_days:
            data = rankings.user_days_played(db, players=shared.players)
        elif ranking_type == RankingStatisticsTypes.user_played_games:
            data = rankings.user_played_games(db, is_active=is_active)
        elif ranking_type == RankingStatisticsTypes.user_completed_games:
            data = rankings.user_completed_games(db, counts=shared.counts)
        elif ranking_type == RankingStatisticsTypes.achievements:
            data = rankings.user_ranking_achievements(db, is_active=is_active)
        elif ranking_type == RankingStatisticsTypes.user_ratio:
            data = rankings.user_ratio(db, counts=shared.counts)
        elif ranking_type == RankingStatisticsTypes.user_current_streak:
            data = rankings.user_current_streak(db, players=shared.players)
        elif ranking_type == RankingStatisticsTypes.user_best_streak:
            data = rankings.user_best_streak(db, players=shared.players)
        elif ranking_type == RankingStatisticsTypes.games_most_played:
            data = rankings.games_most_played(db, is_active=is_active)
        elif ranking_type == RankingStatisticsTypes.platform_played:
            data = rankings.platform_played_games(db, is_active=is_active)
        elif ranking_type == RankingStatisticsTypes.debt:
            data = [{"message": "Debt is not implemented yet"}]
        elif ranking_type == RankingStatisticsTypes.games_last_played:
            data = rankings.games_last_played(db, is_active=is_active)
        else:
            data = {"message": "More rankings are coming"}
        content["type"] = ranking_type
        content["data"] = plain(data)
        response.append(content)
    return response


class UserStatisticsTypes(str, Enum):
    played_games = "played_games"
    completed_games = "completed_games"
    top_games = "top_games"
    achievements = "achievements"
    streak = "streak"


@router.get("/users/{username}")
def get_user_statistics(
    username: str,
    ranking: str = None,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        username (str): _description_
        ranking (str, optional): _description_. Defaults to None.
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    auth.ensure_self_or_admin(active_user, username=username)
    if ranking is not None:
        rankings_list = ranking.split(",")
    else:
        rankings_list = [elem.value for elem in UserStatisticsTypes]

    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    response = []
    for ranking_type in rankings_list:
        content = {}
        if ranking_type == UserStatisticsTypes.played_games:
            data = users.get_games(db, user.id)
        elif ranking_type == UserStatisticsTypes.completed_games:
            data = users.get_games(db=db, user_id=user.id, completed=True)
        elif ranking_type == UserStatisticsTypes.top_games:
            data = users.top_games(db, username)
        elif ranking_type == UserStatisticsTypes.achievements:
            data = users.get_achievements(db, username)
        elif ranking_type == UserStatisticsTypes.streak:
            data = users.get_streaks(db, username)[0]
        else:
            data = {"message": ranking_type + " is not a valid ranking"}
        content["type"] = ranking_type
        content["len_data"] = len(data)
        content["data"] = plain(data)
        response.append(content)
    return response
