import datetime
from enum import Enum

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    Security,
    UploadFile,
)
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..crud import games, time_entries, users
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
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


class RankingUsersTypes(str, Enum):
    games = "games"


@router.get("/", response_model=list[schemas.User])
@version(1)
def get_users(
    admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)
):
    """_summary_

    Args:
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    users_db = users.get_users(db)
    return users_db


@router.get("/{username}", response_model=schemas.User)
@version(1)
def get_user(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        username (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user_db = users.get_user_by_username(db, username)
    if user_db is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return user_db


@router.get("/{username}/weekly-resume")
@version(1)
async def get_weekly_resume(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        username (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user_db = users.get_user_by_username(db, username)
    if user_db is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    resume = await actions.weekly_resume(db, user_db, mode=1, silent=True)
    return resume


# @router.post("/", response_model=schemas.User)
# @version(1)
# def add_user(user: schemas.UserUpdate, db: Session = Depends(get_db)):
#     """
#     Add user
#     """
#     db_user = users.get_user_by_username(db, user.username)
#     if db_user:
#         raise HTTPException(status_code=400, detail="User already registered")
#     return users.create_user(db=db, user=user)


@router.put("/", response_model=schemas.User)
@version(1)
def update_user(
    user: schemas.UserUpdate,
    active_user: models.User = Security(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Update user
    """
    if active_user.username != user.username:
        raise HTTPException(status_code=403, detail=msg.USER_NOT_ADMIN)
    db_user = users.get_user_by_username(db, user.username)
    if db_user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return users.update_user(db=db, user=user)


@router.get("/{username}/profile")
@version(1)
def get_profile(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Main stats, in-progress games and personal data of a user"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return users.get_profile(db, user)


@router.patch("/{username}/profile")
@version(1)
def update_profile(
    username: str,
    body: schemas.UserProfileUpdate,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Edit own name, email and Telegram id"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        data["name"] = data["name"].strip() or None
    if "email" in data:
        data["email"] = (data["email"] or "").strip() or None
        if data["email"] and not utils.validate_email_format(data["email"]):
            raise HTTPException(status_code=400, detail=msg.EMAIL_INVALID)
    users.update_profile(db, user, data)
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "telegram_id": user.telegram_id,
    }


@router.post("/{username}/password")
@version(1)
def change_password(
    username: str,
    body: schemas.PasswordChange,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Change own password (the current one is required)"""
    if active_user.username != username:
        raise HTTPException(status_code=403, detail=msg.USER_NOT_ADMIN)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    if not auth.verify_password(body.current_password, user.password):
        raise HTTPException(status_code=400, detail=msg.PASSWORD_WRONG)
    if not utils.validate_password_requirements(body.new_password):
        raise HTTPException(status_code=400, detail=msg.PASSWORD_RULES)
    users.change_password(db, user, body.new_password)
    return {"message": "Contraseña actualizada"}


@router.post("/{username}/new_game", response_model=schemas.UserGame)
@version(1)
async def add_game_to_user(
    username: str,
    game: schemas.NewGameUser,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Add new game to user list
    """
    auth.ensure_self_or_admin(active_user, username=username)
    current_season = datetime.datetime.now().year
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    already_playing = users.get_game_by_id(db, user.id, game.game_id, current_season)
    if already_playing:
        raise HTTPException(status_code=409, detail=msg.USER_ALREADY_PLAYING)
    try:
        game_db = games.get_game_by_id(db, game.game_id)
        if game_db is None:
            raise HTTPException(status_code=404, detail=msg.GAME_NOT_FOUND)
        return await users.add_new_game(db=db, game=game, user=user)
    except Exception as e:
        logger.info(e)
        raise HTTPException(
            status_code=500, detail="Error adding new game user: " + str(e)
        )


@router.get(
    "/{username}/games",
    response_model=list[schemas.UserGame],
)
@version(1)
def get_games(
    username: str,
    limit: int = None,
    completed: bool = None,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username=username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    played_games = users.get_games(db, user.id, limit, completed)
    return played_games


@router.patch("/{username}/complete-game", response_model=schemas.UserGame)
@version(1)
async def complete_game(
    username: str,
    game_id: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Complete game by username
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    logger.info("USER:")
    logger.info(user)
    if user is None:
        logger.info("IS NONE")
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    current_season = datetime.datetime.now().year
    user_game = users.get_game_by_id(db, user.id, game_id, current_season)
    if user_game is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_PLAYING)
    if user_game.completed == 1:
        raise HTTPException(status_code=409, detail=msg.GAME_ALREADY_COMPLETED)
    try:
        return await users.complete_game(db, user.id, game_id)
    except Exception as e:
        logger.info(e)
        raise HTTPException(
            status_code=500, detail="Error completing game_user: " + str(e)
        )


@router.patch("/{username}/rate-game")
@version(1)
async def rate_game(
    username: str,
    game_id: str,
    score: float,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Rate game
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    current_season = datetime.datetime.now().year
    user_game = users.get_game_by_id(db, user.id, game_id, current_season)
    if user_game is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_PLAYING)
    try:
        return await users.rate_game(db, user.id, game_id, score)
    except Exception as e:
        logger.info(e)
        raise HTTPException(status_code=500, detail="Error rating game_user: " + str(e))


@router.patch("/{username}/avatar")
@version(1)
async def upload_avatar(
    username: str,
    # file: Annotated[UploadFile, File(description="A file read as UploadFile")],
    file: UploadFile,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    auth.ensure_self_or_admin(active_user, username=username)
    allowed_types = ["image/jpeg", "image/jpg", "image/png"]
    if file.content_type not in allowed_types:
        logger.info(msg.FILE_TYPE_NOT_ALLOWED)
        raise HTTPException(
            status_code=400,
            detail=msg.FILE_TYPE_NOT_ALLOWED,
        )
    if not users.get_user_by_username(db, username):
        logger.info(msg.USER_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    logger.info("File size: " + str(file.size))
    if file.size > 2097152:
        logger.info(msg.FILE_TOO_BIG)
        raise HTTPException(status_code=400, detail=msg.FILE_TOO_BIG)
    try:
        data = await file.read()
        users.upload_avatar(db, username, data)
        return "Avatar uploaded"
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{username}/avatar")
@version(1)
async def get_avatar(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    auth.ensure_self_or_admin(active_user, username=username)
    if not users.get_user_by_username(db, username):
        logger.info(msg.USER_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    try:
        data = users.get_avatar(db, username)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not data or not data[0]:
        raise HTTPException(status_code=404, detail="Avatar not found")
    image = bytes(data[0])
    media_type = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    return Response(content=image, media_type=media_type)
