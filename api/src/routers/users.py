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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import auth
from ..crud import games, time_entries, users
from ..database import models, schemas
from ..database.database import SessionLocal
from ..utils import actions as actions
from ..utils import images
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.logger import LogManager
from ..utils import seasons, user_settings

log_manager = LogManager()
logger = log_manager.get_logger()

AVATAR_MAX_BYTES = 2 * 1024 * 1024

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
    resume = await actions.weekly_resume(db, user_db, weeks_ago=0, silent=True)
    return resume


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
    if "name" in data:
        # never empty: messages and rankings print it (falls back to the nickname)
        data["name"] = (data["name"] or "").strip() or user.username
    if "email" in data:
        # the email is the login identifier: it can be changed but not removed
        data["email"] = utils.normalize_email(data["email"])
        if not data["email"]:
            raise HTTPException(status_code=400, detail=msg.EMAIL_REQUIRED)
        if not utils.validate_email_format(data["email"]):
            raise HTTPException(status_code=400, detail=msg.EMAIL_INVALID)
        if users.email_in_use(db, data["email"], exclude_user_id=user.id):
            raise HTTPException(status_code=400, detail=msg.EMAIL_IN_USE)
    if data.get("telegram_id") is not None and users.telegram_id_in_use(db, data["telegram_id"], exclude_user_id=user.id):
        raise HTTPException(status_code=400, detail=msg.TELEGRAM_ID_IN_USE)
    users.update_profile(db, user, data)
    return {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "telegram_id": user.telegram_id,
    }


@router.get("/{username}/settings")
@version(1)
def get_settings(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Personal preferences (None = the default applies) and the defaults"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return user_settings.get(db, user.id)


@router.patch("/{username}/settings")
@version(1)
def update_settings(
    username: str,
    body: schemas.UserSettingsUpdate,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Change personal preferences; null resets one to its default"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    changes = body.model_dump(exclude_unset=True)
    hours = changes.get("forgotten_timer_hours")
    if hours is not None and not user_settings.valid_forgotten_timer_hours(hours):
        raise HTTPException(
            status_code=400,
            detail=msg.FORGOTTEN_HOURS_INVALID.format(
                min=user_settings.MIN_FORGOTTEN_TIMER_HOURS, max=user_settings.MAX_FORGOTTEN_TIMER_HOURS
            ),
        )
    return user_settings.update(db, user.id, changes)


@router.post("/{username}/password")
@version(1)
def change_password(
    username: str,
    body: schemas.PasswordChange,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Change own password (the current one is required)"""
    auth.ensure_self(active_user, username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    if not auth.verify_password(body.current_password, user.password):
        raise HTTPException(status_code=400, detail=msg.PASSWORD_WRONG)
    if not utils.validate_password_requirements(body.new_password):
        raise HTTPException(status_code=400, detail=msg.PASSWORD_RULES)
    users.change_password(db, user, body.new_password)
    return {"message": "Contraseña actualizada"}


@router.get("/{username}/library")
@version(1)
def get_library(
    username: str,
    limit: int = Query(15, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every game of the user (all seasons), most recently played first"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return users.get_library(db, user.id, limit, offset)


def _check_completion_date(entry: models.UserGame, date: datetime.date):
    if date > datetime.date.today():
        raise HTTPException(status_code=400, detail=msg.COMPLETION_DATE_FUTURE)
    if date.year != entry.season:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha de completado debe estar en la temporada {entry.season}",
        )
    if entry.started_date and date < entry.started_date:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha de completado no puede ser anterior al inicio ({entry.started_date})",
        )


@router.patch("/{username}/library/{entry_id}/completion")
@version(1)
async def update_completion(
    username: str,
    entry_id: int,
    body: schemas.CompletionUpdate,
    silent: bool = False,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Complete a library entry, change its completion date or unmark it.

    - completed=true on a pending entry completes it: only in the current
      season and once per game and season (announced unless silent=true).
    - completed=true + completed_date on an already completed entry changes
      the date (must fall inside the entry's season).
    - completed=false unmarks it (any season); the entry itself is kept.
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    entry = users.get_library_entry(db, user.id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=msg.ENTRY_NOT_FOUND)

    if not body.completed:
        if entry.completed:
            users.uncomplete_entry(db, entry)
    elif not entry.completed:
        if entry.season != seasons.current():
            raise HTTPException(status_code=409, detail=msg.COMPLETE_ONLY_CURRENT_SEASON)
        if users.completed_in_season(db, user.id, entry.game_id, entry.season):
            raise HTTPException(status_code=409, detail=msg.ALREADY_COMPLETED_IN_SEASON)
        date = body.completed_date or datetime.date.today()
        _check_completion_date(entry, date)
        await users.complete_entry(db, entry, date, silent)
    else:
        if body.completed_date is None:
            raise HTTPException(status_code=409, detail=msg.GAME_ALREADY_COMPLETED)
        _check_completion_date(entry, body.completed_date)
        users.set_completed_date(db, entry, body.completed_date)
    return users.get_library_item(db, user.id, entry.id)


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
    current_season = seasons.current()
    user = users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    already_playing = users.get_game_by_id(db, user.id, game.game_id, current_season)
    if already_playing:
        raise HTTPException(status_code=409, detail=msg.USER_ALREADY_PLAYING)
    if games.get_game_by_id(db, game.game_id) is None:
        raise HTTPException(status_code=404, detail=msg.GAME_NOT_FOUND)
    try:
        return await users.add_new_game(db=db, game=game, user=user)
    except SQLAlchemyError as e:
        logger.error("Error adding new game user: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


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
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    current_season = seasons.current()
    user_game = users.get_game_by_id(db, user.id, game_id, current_season)
    if user_game is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_PLAYING)
    if user_game.completed == 1:
        raise HTTPException(status_code=409, detail=msg.GAME_ALREADY_COMPLETED)
    try:
        return await users.complete_game(db, user.id, game_id)
    except SQLAlchemyError as e:
        logger.error("Error completing game_user: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


@router.patch("/{username}/rate-game")
@version(1)
async def rate_game(
    username: str,
    game_id: str,
    score: float = Query(..., ge=0, le=10),
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
    current_season = seasons.current()
    user_game = users.get_game_by_id(db, user.id, game_id, current_season)
    if user_game is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_PLAYING)
    try:
        return await users.rate_game(db, user.id, game_id, score)
    except Exception as e:
        logger.info(e)
        logger.error("Error rating game: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


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
    if not users.get_user_by_username(db, username):
        logger.info(msg.USER_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    data = await file.read(AVATAR_MAX_BYTES + 1)
    try:
        images.validate_image(data, AVATAR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=msg.FILE_TOO_BIG if str(e) == "too_big" else msg.FILE_TYPE_NOT_ALLOWED)
    try:
        users.upload_avatar(db, username, data)
        return "Avatar uploaded"
    except Exception as e:
        logger.error("Error saving avatar: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


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
        logger.error("Error reading avatar: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)
    if not data or not data[0]:
        raise HTTPException(status_code=404, detail="Avatar not found")
    image = bytes(data[0])
    media_type = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    return Response(content=image, media_type=media_type)
