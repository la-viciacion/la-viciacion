from fastapi import APIRouter, Depends, HTTPException, Response, Security, UploadFile
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import games, time_entries, users
from ..crud.achievements import Achievements
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import images
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

achievements = Achievements()

# To add dependency for active user: dependencies=[Depends(auth.get_current_active_user)],
ACHIEVEMENT_IMAGE_MAX_BYTES = 1024000

router = APIRouter(
    prefix="/utils",
    tags=["Utils"],
    responses={404: {"description": "Not found"}},
)


@router.get("/platforms")
@version(1)
def platforms(
    db: Session = Depends(get_db),
    user: models.User = Security(auth.get_current_active_user),
):
    """
    Get platforms list
    """
    tags = utils.get_platforms(db)
    response = []
    for tag in tags:
        response.append({"id": tag[0], "name": tag[1]})
    return response


@router.get("/achievements")
@version(1)
def achievements_list(
    db: Session = Depends(get_db),
    user: models.User = Security(auth.get_current_active_user),
):
    """
    Get achievements list
    """
    ach_list = achievements.get_achievements_list(db)
    response = []
    for ach in ach_list:
        response.append(ach.title)
    return response


@router.get("/playing")
@version(1)
def get_playing_users(
    db: Session = Depends(get_db),
    user_logged: models.User = Security(auth.get_current_active_user),
):
    """
    Get playing users
    """
    users_db = users.get_users(db)
    playing = []
    for user in users_db:
        info = {}
        active_game_timer = time_entries.get_active_game_timer_by_user(db, user.id)
        if active_game_timer is not None:
            logger.info(active_game_timer)
            info["user"] = user.name
            info["game"] = games.get_game_by_id(db, active_game_timer.game_id).name
            info["time"] = active_game_timer.start_time
            playing.append(info)
    return playing


@router.patch("/achievement-image/{achievement}")
@version(1)
async def upload_achievement_image(
    achievement: str,
    # file: Annotated[UploadFile, File(description="A file read as UploadFile")],
    file: UploadFile,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.require_admin),
):
    """
    Upload achievement image
    """
    if not achievements.get_ach_by_key(db, achievement):
        logger.info(msg.ACHIEVEMENT_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.ACHIEVEMENT_NOT_EXISTS)
    data = await file.read(ACHIEVEMENT_IMAGE_MAX_BYTES + 1)
    try:
        images.validate_image(data, ACHIEVEMENT_IMAGE_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=msg.FILE_TOO_BIG_ACHIEVEMENTS if str(e) == "too_big" else msg.FILE_TYPE_NOT_ALLOWED,
        )
    try:
        achievements.upload_image(db, achievement, data)
        return "Image uploaded"
    except Exception as e:
        logger.error("Error saving achievement image: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


@router.get("/achievement-image/{achievement}")
@version(1)
async def get_achievement_image(
    achievement: str,
    db: Session = Depends(get_db),
):
    """
    Get achievement image
    """
    if not achievements.get_ach_by_key(db, achievement):
        logger.info(msg.ACHIEVEMENT_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.ACHIEVEMENT_NOT_EXISTS)
    try:
        data = achievements.get_image(db, achievement)
        if data[0] is None:
            return Response(content="Achievement has no image", status_code=400)
        return Response(content=data[0], media_type=images.media_type_of(data[0]))
    except Exception as e:
        logger.error("Error reading achievement image: " + str(e))
        raise HTTPException(status_code=500, detail=msg.INTERNAL_ERROR)


# @router.get("/sentry-debug")
# @version(1)
# async def trigger_error():
#     division_by_zero = 1 / 0
