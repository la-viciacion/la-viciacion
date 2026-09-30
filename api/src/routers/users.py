import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import users
from ..database import models, schemas
from ..utils import actions, images
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


def _target_user(db: Session, active_user: models.User, username: str) -> models.User:
    """The user a route is about. Most of the time it is the caller, already loaded by the auth
    dependency in this same request: an admin asking about somebody else costs the lookup."""
    user = active_user if active_user.username == username else users.get_user_by_username(db, username)
    if user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return user


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
    user_db = _target_user(db, active_user, username)
    return user_db


@router.get("/{username}/profile")
@version(1)
def get_profile(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Main stats, in-progress games and personal data of a user"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
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
    user = _target_user(db, active_user, username)
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
    user = _target_user(db, active_user, username)
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
    user = _target_user(db, active_user, username)
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
    user = _target_user(db, active_user, username)
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
    user = _target_user(db, active_user, username)
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
def update_completion(
    username: str,
    entry_id: int,
    body: schemas.CompletionUpdate,
    background_tasks: BackgroundTasks,
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
    user = _target_user(db, active_user, username)
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
        users.complete_entry(db, entry, date)
        # the notice and the achievements take seconds (HLTB, OpenAI, Telegram): not in this request
        background_tasks.add_task(actions.after_completion, entry.id, silent)
    else:
        if body.completed_date is None:
            raise HTTPException(status_code=409, detail=msg.GAME_ALREADY_COMPLETED)
        _check_completion_date(entry, body.completed_date)
        users.set_completed_date(db, entry, body.completed_date)
    return users.get_library_item(db, user.id, entry.id)


@router.patch("/{username}/avatar")
@version(1)
def upload_avatar(
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
    data = file.file.read(AVATAR_MAX_BYTES + 1)
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
def get_avatar(
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
    return Response(content=image, media_type=images.media_type_of(image))
