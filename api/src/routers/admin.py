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
        achievements.populate_achievements(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return "Init completed!"


@router.get("/sync-data")
@version(1)
async def sync_data(
    api_key: None = Security(auth.get_api_key),
    sync_season: bool = Query(
        default=False,
        title="Reset season data",
        description="Reset and recompute all current-season statistics",
    ),
    silent: bool = Query(
        default=False,
        title="Run in silent mode",
        description="Disable Telegram notifications",
    ),
    sync_all: bool = Query(
        default=False,
        title="Reset all data",
        description="Reset and recompute all statistics from scratch",
    ),
    only_acive_users: bool = Query(
        default=True,
        title="Sync only active users",
        description="Recompute only active users",
    ),
    db: Session = Depends(get_db),
):
    """Recompute stats/rankings/achievements from current session data."""
    try:
        await actions.recompute_all_users_and_rankings(
            db,
            silent=silent,
            sync_season=sync_season,
            sync_all=sync_all,
            only_active_users=only_acive_users,
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
        raise HTTPException(status_code=409, detail=msg.ACCOUNT_ALREADY_ACTIVATED)
    else:
        return {"message": "Account activated successfully"}


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
