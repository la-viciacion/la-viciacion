from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    Security,
    UploadFile,
    status,
)
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..config import Config
from ..crud import users
from ..crud.achievements import Achievements
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils import messages as msg
from ..utils.email import Email
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

config = Config()
achievements = Achievements()
email = Email()

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    responses={404: {"description": "Not found"}},
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/")
@version(1)
def test_endpoint(user: models.User = Security(auth.get_current_active_user)):
    """_summary_

    Args:
        user (models.User, optional): _description_. Defaults to Security(auth.get_current_active_user).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail=msg.USER_NOT_ADMIN)
    return "Gratz! You are an admin."


@router.get("/init")
@version(1)
def init(
    db: Session = Depends(get_db),
    api_key: None = Security(auth.get_api_key),
):
    """_summary_

    Args:
        db (Session, optional): _description_. Defaults to Depends(get_db).
        api_key (None, optional): _description_. Defaults to Security(auth.get_api_key).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    try:
        logger.info("Creating admin users")
        for admin in config.ADMIN_USERS:
            users.create_admin_user(db, admin)
        achievements.populate_achievements(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return "Init completed!"


@router.get("/sync-data")
@version(1)
async def sync_data(
    api_key: None = Security(auth.get_api_key),
    user_clfy_id: str = Query(
        default=None,
        title="User Clockify ID",
        description="Sync data for the user with this Clockify ID",
    ),
    sync_season: bool = Query(
        default=False,
        title="Sync all season data",
        description="Sync all time entries for the current year",
    ),
    silent: bool = Query(
        default=False,
        title="Run in silent mode",
        description="Disable Telegram notifications",
    ),
    sync_all: bool = Query(
        default=False,
        title="Sync all data",
        description="Sync all time entries for the whole time",
    ),
    only_acive_users: bool = Query(
        default=True,
        title="Sync only active users",
        description="Sync only entries for active users",
    ),
    only_time_entries: bool = Query(
        default=False,
        title="Sync only time entries",
        description="Sync all time entries for the whole time, but not calculate anything",
    ),
    db: Session = Depends(get_db),
):
    """Sync data from Clockify

    Args:
        api_key (None, optional): API Key. Defaults to Security(auth.get_api_key).
        sync_season (bool, optional): Select if sync entire current season. Defaults to Query( default=None, title="Sync all season data", description="Sync all time entries for the current year", ).
        silent (bool, optional): Sync data without send Telegram notifications. Defaults to Query( default=None, title="Run in silent mode", description="Disable Telegram notifications", ).
        sync_all (bool, optional): Sync entire data (from the very beginning). Defaults to Query( default=None, title="Sync all data", description="Sync all time entries for the whole time", ).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    try:
        # for admin in config.ADMIN_USERS:
        #     users.create_admin_user(db, admin)
        await actions.sync_data(
            db,
            user_clfy_id=user_clfy_id,
            sync_season=sync_season,
            silent=silent,
            sync_all=sync_all,
            only_acive_users=only_acive_users,
            only_time_entries=only_time_entries,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "Sync completed!"}


@router.put("/update_user", response_model=schemas.User)
@version(1)
def update_user(
    user_data: schemas.UserUpdateForAdmin,
    # api_key: None = Security(auth.get_api_key),
    user: models.User = Security(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        api_key (None, optional): API Key. Defaults to Security(auth.get_api_key).
        user_data (schemas.UserUpdateForAdmin): _description_
        user (models.User, optional): _description_. Defaults to Security(auth.get_current_active_user).
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail=msg.USER_NOT_ADMIN)
    db_user = users.get_user_by_username(db, user_data.username)
    if db_user is None:
        raise HTTPException(status_code=404, detail=msg.USER_NOT_EXISTS)
    return users.update_user_as_admin(db=db, user=user_data)


@router.get("/activate/{username}")
@version(1)
def activate_account(
    username: str,
    db: Session = Depends(get_db),
    api_key: None = Security(auth.get_api_key),
):
    """_summary_

    Args:
        username (str): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).
        api_key (None, optional): _description_. Defaults to Security(auth.get_api_key).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    if users.activate_account(db, username):
        return msg.ACCOUNT_ALREADY_ACTIVATED
    else:
        raise HTTPException(status_code=409, detail=msg.ACCOUNT_ALREADY_ACTIVATED)


@router.post("/send_email")
@version(1)
def send_email(
    info: schemas.Email,
    api_key: None = Security(auth.get_api_key),
):
    """_summary_

    Args:
        info (schemas.Email): _description_
        api_key (None, optional): _description_. Defaults to Security(auth.get_api_key).

    Returns:
        _type_: _description_
    """
    return email.send_mail(
        receivers=info.receiver, subject=info.subject, msg=info.message
    )
