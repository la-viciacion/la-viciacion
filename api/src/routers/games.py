from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import game_catalog, game_overview, games
from ..database import models, schemas
from ..utils import messages
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

router = APIRouter(
    prefix="/games",
    tags=["Games"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


@router.get("/", response_model=list[schemas.Game])
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


@router.get("/search-rawg", response_model=list[schemas.RawgGameCandidate])
async def search_rawg(query: str, db: Session = Depends(get_db)):
    """Search games on RAWG.io and return candidates with DB existence status."""
    if not query or len(query.strip()) < 2:
        raise HTTPException(
            status_code=400, detail="Query must be at least 2 characters long"
        )
    return await utils.search_rawg_games(query.strip(), db=db)


@router.get("/catalog")
def get_game_catalog(
    q: str | None = Query(None, description="Part of the name"),
    genre: str | None = None,
    library: str | None = Query(None, pattern="^(have|not)$", description="In (have) or not in (not) your library"),
    completed: bool = Query(False, description="Only the ones you completed"),
    rated: bool = Query(False, description="Only the ones you rated"),
    playing: bool = Query(False, description="Only the ones somebody is playing right now"),
    with_players: bool = Query(False, description="Only the ones somebody has in their library"),
    sort: str = Query("activity", pattern="^(activity|played|rated|players|release|name)$"),
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every game with what the group has done with it (derived), filtered, ordered and paged"""
    return game_catalog.catalog(
        db, current_user.id, q=q, genre=genre, library=library, completed=completed, rated=rated,
        playing=playing, with_players=with_players, sort=sort, limit=limit, offset=offset,
    )


@router.get("/{game_id}/overview")
def get_game_overview(
    game_id: str,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The game page: who of the group has it, their hours, completions and ratings (derived, nothing stored)"""
    found = game_overview.overview(db, game_id, current_user.id)
    if found is None:
        raise HTTPException(status_code=404, detail="Game not exists")
    return found


@router.get("/{game_id}", response_model=schemas.Game)
def get_game_by_id(game_id: str, db: Session = Depends(get_db)):
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


@router.post("/", response_model=schemas.Game, status_code=201)
async def create_game(game: schemas.NewGame, db: Session = Depends(get_db)):
    """Add a new game to DB: from its RAWG entry when `rawg_id` is given, as typed otherwise (only the name is required)."""
    # the duplicate check and the stored name must see the same text: " Celeste" is "Celeste"
    game.name = game.name.strip()
    if not game.name:
        raise HTTPException(status_code=400, detail=messages.GAME_NAME_EMPTY)
    await run_in_threadpool(_refuse_duplicates, db, game)
    return await games.new_game(db=db, game=game)


def _refuse_duplicates(db: Session, game: schemas.NewGame) -> None:
    if game.rawg_id:
        existing = (
            db.query(models.Game)
            .filter(models.Game.rawg_id == game.rawg_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail=messages.GAME_ALREADY_IN_CATALOGUE)

    games_db = games.get_game_by_name(db, game.name)
    for game_db in games_db:
        if game_db.name.strip().lower() == game.name.strip().lower():
            raise HTTPException(status_code=400, detail=messages.GAME_ALREADY_IN_CATALOGUE)


@router.put("/{game_id}", response_model=schemas.Game, status_code=200)
def update_game(
    game_id: str,
    game: schemas.UpdateGame,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
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
