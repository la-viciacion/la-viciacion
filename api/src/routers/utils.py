from fastapi import APIRouter, Depends, HTTPException, Response, Security, UploadFile
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud.achievements import Achievements
from ..database import models
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


@router.patch("/achievement-image/{achievement}")
def upload_achievement_image(
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
    data = file.file.read(ACHIEVEMENT_IMAGE_MAX_BYTES + 1)
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
def get_achievement_image(
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
