from enum import Enum

from fastapi import APIRouter, Depends
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..crud import rankings, users
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

router = APIRouter(
    prefix="/statistics",
    tags=["Statistics"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
@version(1)
def get_ranking_statistics(
    ranking: str = None,
    db: Session = Depends(get_db),
):
    """
    Get general rankings. To retrieve only specific rankings, add 'ranking' param with desired rankings, separated by comma (,).

    Allowed values: 'user_hours', 'user_days', 'user_played_games',
    'user_completed_games', 'achievements', 'user_ratio', 'user_current_streak',
    'user_best_streak', 'games_most_played', 'platform_played', 'debt', 'games_last_played'
    """
    if ranking is not None:
        rankings_list = ranking.split(",")
    else:
        rankings_list = [elem.value for elem in RankingStatisticsTypes]
    response = []
    for ranking_type in rankings_list:
        content = {}
        if ranking_type == RankingStatisticsTypes.user_hours:
            data = rankings.user_hours_players(db)
        elif ranking_type == RankingStatisticsTypes.user_days:
            data = rankings.user_days_played(db)
        elif ranking_type == RankingStatisticsTypes.user_played_games:
            data = rankings.user_played_games(db)
        elif ranking_type == RankingStatisticsTypes.user_completed_games:
            data = rankings.user_completed_games(db)
        elif ranking_type == RankingStatisticsTypes.achievements:
            data = rankings.user_ranking_achievements(db)
        elif ranking_type == RankingStatisticsTypes.user_ratio:
            data = rankings.user_ratio(db)
        elif ranking_type == RankingStatisticsTypes.user_current_streak:
            data = rankings.user_current_streak(db)
        elif ranking_type == RankingStatisticsTypes.user_best_streak:
            data = rankings.user_best_streak(db)
        elif ranking_type == RankingStatisticsTypes.games_most_played:
            data = rankings.games_most_played(db)
        elif ranking_type == RankingStatisticsTypes.platform_played:
            data = rankings.platform_played_games(db)
        elif ranking_type == RankingStatisticsTypes.debt:
            data = [{"message": "Debt is not implemented yet"}]
        elif ranking_type == RankingStatisticsTypes.games_last_played:
            data = rankings.games_last_played(db)
        else:
            data = {"message": "More rankings are coming"}
        content["type"] = ranking_type
        content["data"] = data
        response.append(content)
    return response


class UserStatisticsTypes(str, Enum):
    played_games = "played_games"
    completed_games = "completed_games"
    top_games = "top_games"
    achievements = "achievements"
    streak = "streak"


@router.get("/users/{username}")
@version(1)
def get_user_statistics(
    username: str,
    ranking: str = None,
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
    if ranking is not None:
        rankings_list = ranking.split(",")
    else:
        rankings_list = [elem.value for elem in UserStatisticsTypes]
    response = []
    for ranking_type in rankings_list:
        content = {}
        if ranking_type == UserStatisticsTypes.played_games:
            user = users.get_user_by_username(db, username)
            data = users.get_games(db, user.id)
            # data = users.played_games(db=db, username=username)
        elif ranking_type == UserStatisticsTypes.completed_games:
            user = users.get_user_by_username(db, username)
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
        content["data"] = data
        response.append(content)
    return response
