from fastapi import APIRouter, Depends, HTTPException
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..crud import games
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

router = APIRouter(
    prefix="/games",
    tags=["Games"],
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


@router.get("/", response_model=list[schemas.Game])
@version(1)
def get_games(name: str = None, limit: int = None, db: Session = Depends(get_db)):
    """_summary_

    Args:
        name (str, optional): _description_. Defaults to None.
        limit (int, optional): _description_. Defaults to None.
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    logger.info("Getting games...")
    if name is None:
        games_db = games.get_games(db, limit)
    else:
        games_db = games.get_game_by_name(db, name)
    return games_db


@router.get("/{game_id}", response_model=schemas.Game)
@version(1)
async def get_game_by_id(game_id: str, db: Session = Depends(get_db)):
    """_summary_

    Args:
        game_id (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    game_db = games.get_game_by_id(db, game_id)
    if game_db is None:
        raise HTTPException(status_code=404, detail="Game not exists")

    return game_db


# @router.get("/games/name/{name}", tags=["Games"], response_model=schemas.Game)
# @version(1)
# async def get_game_by_name(name: str, db: Session = Depends(get_db)):
#     """
#     Get game from DB by name
#     """
#     game_db = games.get_game_by_name(db, name)
#     if game_db is None:
#         raise HTTPException(status_code=404, detail="Game not exists")
#     return game_db


@router.get("/rawg/{name}")
@version(1)
async def get_game_rawg_by_name(name: str, db: Session = Depends(get_db)):
    """_summary_

    Args:
        name (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    game_info = await utils.get_game_info(name)
    return game_info


@router.post("/", response_model=schemas.Game, status_code=201)
@version(1)
async def create_game(game: schemas.NewGame, db: Session = Depends(get_db)):
    """_summary_

    Args:
        game (schemas.NewGame): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    games_db = games.get_game_by_name(db, game.name)
    for game_db in games_db:
        if game_db.name == game.name:
            raise HTTPException(status_code=400, detail="Game already in DB")
    return await games.new_game(db=db, game=game)


@router.put("/{game_id}", response_model=schemas.Game, status_code=200)
@version(1)
async def update_game(
    game_id: str, game: schemas.UpdateGame, db: Session = Depends(get_db)
):
    """_summary_

    Args:
        game_id (str): _description_
        game (schemas.UpdateGame): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    game_db = games.get_game_by_id(db, game_id)
    if game_db is None:
        raise HTTPException(status_code=404, detail="Game not exists")
    return games.update_game(db=db, game_id=game_id, game=game)


@router.get("/recommendations/{user_id}")
@version(1)
async def get_recommendations(
    user_id: int, genres: str = None, limit: int = None, db: Session = Depends(get_db)
):
    """_summary_

    Args:
        name (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    genres_list = []
    if genres is not None:
        genres_list = genres.split(",")
    recommended_games = games.recommended_games(
        db, user_id, genres=genres_list, limit=limit
    )
    games_list = []
    for rec_game in recommended_games:
        game = {}
        game["game_id"] = rec_game[0]
        game["user_id"] = rec_game[1]
        game["game_name"] = rec_game[2]
        game["genres"] = rec_game[3]
        game["user_name"] = rec_game[4]
        games_list.append(game)

    return {"num_games": len(games_list), "games": games_list}
