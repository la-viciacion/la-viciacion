import imghdr

from fastapi import APIRouter, Depends, HTTPException, Response, Security, UploadFile
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..crud import games, time_entries, users
from ..crud.achievements import Achievements
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

achievements = Achievements()

# To add dependency for active user: dependencies=[Depends(auth.get_current_active_user)],
router = APIRouter(
    prefix="/utils",
    tags=["Utils"],
    responses={404: {"description": "Not found"}},
)


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        active_timer = time_entries.get_active_time_entry_by_user(db, user)
        if active_timer is not None:
            logger.info(active_timer)
            info["user"] = user.name
            info["game"] = games.get_game_by_id(
                db, active_timer.project_clockify_id
            ).name
            info["time"] = active_timer.start
            playing.append(info)
    return playing


@router.patch("/achievement-image/{achievement}")
@version(1)
async def upload_achievement_image(
    achievement: str,
    # file: Annotated[UploadFile, File(description="A file read as UploadFile")],
    file: UploadFile,
    db: Session = Depends(get_db),
    user: models.User = Security(auth.get_current_active_user),
):
    """
    Upload achievement image
    """
    allowed_types = ["image/jpeg", "image/jpg", "image/png"]
    if file.content_type not in allowed_types:
        logger.info(msg.FILE_TYPE_NOT_ALLOWED)
        raise HTTPException(
            status_code=400,
            detail=msg.FILE_TYPE_NOT_ALLOWED,
        )
    if not achievements.get_ach_by_key(db, achievement):
        logger.info(msg.ACHIEVEMENT_NOT_EXISTS)
        raise HTTPException(status_code=404, detail=msg.ACHIEVEMENT_NOT_EXISTS)
    logger.info("File size: " + str(file.size))
    if file.size > 1024000:
        logger.info(msg.FILE_TOO_BIG_ACHIEVEMENTS)
        raise HTTPException(status_code=400, detail=msg.FILE_TOO_BIG)
    try:
        data = await file.read()
        achievements.upload_image(db, achievement, data)
        return "Image uploaded"
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/achievement-image/{achievement}")
@version(1)
async def get_achievement_image(
    achievement: str,
    db: Session = Depends(get_db),
    # api_key: None = Security(auth.get_api_key),
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
        format_type = imghdr.what(None, h=data[0])
        # print(format_type)
        return Response(content=data[0], media_type="image/" + format_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/sentry-debug")
# @version(1)
# async def trigger_error():
#     division_by_zero = 1 / 0
