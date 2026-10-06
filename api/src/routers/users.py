import datetime
import re

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import data_export, games, scores, users, wishlist
from ..database import models, schemas
from ..utils import actions, images
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.logger import LogManager
from ..utils import seasons, user_settings

log_manager = LogManager()
logger = log_manager.get_logger()

# Importing a player's data is switched off for now (the profile hides it too); the route and crud/data_export.py
# stay, so turning it back on is this one constant.
IMPORT_ENABLED = False

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
def get_profile(
    username: str,
    season: str | None = Query(None, pattern=r"^(all|\d{4})$", description="A year, or 'all' for the totals; default: the running season"),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Main stats, in-progress games and personal data of a user"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    return users.get_profile(db, user, seasons.ALL if season == "all" else int(season) if season else None)


@router.patch("/{username}/profile")
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
    minutes = changes.get("timer_notice_minutes")
    if minutes is not None and not user_settings.valid_timer_notice_minutes(minutes):
        raise HTTPException(
            status_code=400,
            detail=msg.TIMER_NOTICE_MINUTES_INVALID.format(
                min=user_settings.MIN_TIMER_NOTICE_MINUTES, max=user_settings.MAX_TIMER_NOTICE_MINUTES
            ),
        )
    return user_settings.update(db, user.id, changes)


@router.post("/{username}/password")
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
def get_library(
    username: str,
    limit: int = Query(15, ge=1, le=100),
    offset: int = Query(0, ge=0),
    game_id: str | None = Query(None, description="Only the entries of this game"),
    season: int | None = Query(None, description="Only the entries of this season (default: every season)"),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The games of the user (every season unless one is asked for), most recently played first"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    return users.get_library(db, user.id, limit, offset, game_id, season)


@router.get("/{username}/recommendations")
def get_recommendations(
    username: str,
    limit: int = Query(12, ge=1, le=50),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Games the other players have and the user has never had, the most shared first"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    return games.recommendations_for(db, user.id, limit)


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
    - completed=false unmarks it; the entry itself is kept.
    - the completion of a closed season is frozen: neither unmarked nor re-dated.
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    entry = users.get_library_entry(db, user.id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=msg.ENTRY_NOT_FOUND)
    if entry.completed and entry.season != seasons.current():
        raise HTTPException(status_code=409, detail=msg.COMPLETION_SEASON_CLOSED)

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


@router.patch("/{username}/library/{entry_id}/abandoned")
def update_abandoned(
    username: str,
    entry_id: int,
    body: schemas.AbandonUpdate,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Mark a library entry as abandoned, or take the mark back.

    - only the running season: a closed one is frozen, as its completion is.
    - a completed entry cannot be abandoned (it was finished).
    - playing the game again resumes it by itself (see crud.users.is_abandoned).
    """
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    entry = users.get_library_entry(db, user.id, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=msg.ENTRY_NOT_FOUND)
    if entry.season != seasons.current():
        raise HTTPException(status_code=409, detail=msg.ABANDON_ONLY_CURRENT_SEASON)
    if body.abandoned and entry.completed:
        raise HTTPException(status_code=409, detail=msg.ABANDON_COMPLETED)
    users.set_abandoned(db, entry, body.abandoned, datetime.datetime.now())
    return users.get_library_item(db, user.id, entry.id)


def _rated_game(db: Session, user: models.User, game_id: str) -> None:
    """Only a game of the user's library (any season) can be rated."""
    if not db.query(models.UserGame.id).filter_by(user_id=user.id, game_id=game_id).first():
        raise HTTPException(status_code=404, detail=msg.GAME_NOT_IN_LIBRARY)


@router.put("/{username}/games/{game_id}/score")
def rate_game(
    username: str,
    game_id: str,
    body: schemas.ScoreUpdate,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Rate a game from 1 to 100 (or change the rating): one per game, whatever the season or platform."""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    _rated_game(db, user, game_id)
    scores.set_score(db, user.id, game_id, body.score)
    db.commit()
    return {"game_id": game_id, "score": body.score}


@router.delete("/{username}/games/{game_id}/score")
def remove_game_score(
    username: str,
    game_id: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove the rating of a game (nothing happens if it had none)."""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    scores.clear_score(db, user.id, game_id)
    db.commit()
    return {"game_id": game_id, "score": None}


@router.put("/{username}/wishlist/{game_id}")
def wish_game(
    username: str,
    game_id: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Add a game to the wishlist (nothing happens if it already is there). A game of your library cannot be wished."""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    if games.get_game_by_id(db, game_id) is None:
        raise HTTPException(status_code=404, detail=msg.GAME_NOT_FOUND)
    if wishlist.in_library(db, user.id, game_id):
        raise HTTPException(status_code=409, detail=msg.GAME_ALREADY_IN_LIBRARY)
    wishlist.add(db, user.id, game_id)
    db.commit()
    return {"game_id": game_id, "wished": True}


@router.delete("/{username}/wishlist/{game_id}")
def unwish_game(
    username: str,
    game_id: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove a game from the wishlist (nothing happens if it was not there)."""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    wishlist.remove(db, user.id, game_id)
    db.commit()
    return {"game_id": game_id, "wished": False}


@router.get("/{username}/export")
def export_data(
    username: str,
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Everything that belongs to the user (sessions, library, ratings, wishlist, achievements) as a file to keep"""
    auth.ensure_self_or_admin(active_user, username=username)
    user = _target_user(db, active_user, username)
    now = datetime.datetime.now()
    name = re.sub(r"[^A-Za-z0-9_-]", "_", user.username)
    return JSONResponse(
        content=jsonable_encoder(data_export.export_user(db, user, now)),
        headers={"Content-Disposition": f'attachment; filename="laviciacion-{name}-{now.date()}.json"'},
    )


@router.post("/{username}/import")
def import_data(
    username: str,
    body: schemas.ExportFile,
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(False, description="Only say what would happen: nothing is written"),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Merge an export file into the account without overwriting anything (see crud/data_export.py)"""
    auth.ensure_self_or_admin(active_user, username=username)
    if not IMPORT_ENABLED:
        raise HTTPException(status_code=404, detail=msg.IMPORT_DISABLED)
    user = _target_user(db, active_user, username)
    if not data_export.is_supported(body):
        raise HTTPException(status_code=400, detail=msg.IMPORT_NOT_A_FILE)
    try:
        report = data_export.import_data(db, active_user, user, body, dry_run)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=msg.IMPORT_CONFLICT)
    if report["sessions"]["imported"] and not dry_run:
        # earned, not imported: the achievements the new sessions deserve are awarded without announcing them
        background_tasks.add_task(actions.after_session_change, user.id, True)
    return report


@router.patch("/{username}/avatar")
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
    try:
        data = images.normalize_image(file.file.read(images.MAX_UPLOAD_BYTES + 1), images.AVATAR_MAX_SIDE)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=images.upload_error(e))
    try:
        users.upload_avatar(db, username, data)
        return "Avatar uploaded"
    except Exception as e:
        logger.error("Error saving avatar: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


@router.get("/photo/{player_id}")
def get_player_photo(
    player_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """The photo of an active player, for every logged-in user: the group sees each other (the chip of who is
    playing now). Unlike /{username}/avatar it is not limited to the owner on purpose; it only ever returns an
    image, and nothing for inactive accounts or the emergency account."""
    row = (
        db.query(models.User.avatar)
        .filter(models.User.id == player_id, models.User.is_active == 1, models.not_god())
        .first()
    )
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return images.cached_image(request, bytes(row[0]), "private, max-age=300")


@router.get("/{username}/avatar")
def get_avatar(
    username: str,
    request: Request,
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
    # always revalidated (a 304 costs no picture): a new avatar must show at once on the owner's own screen
    return images.cached_image(request, bytes(data[0]), "private, no-cache")
