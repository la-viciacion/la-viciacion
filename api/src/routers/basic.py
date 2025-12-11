from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..config import Config
from ..crud import users
from ..database import models, schemas
from ..database.database import SessionLocal, engine
from ..utils import actions as actions
from ..utils import my_utils as utils
from ..utils.custom_exceptions import CustomExceptions
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

models.Base.metadata.create_all(bind=engine)

config = Config()

router = APIRouter(
    tags=["Basic"],
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
def hello_world(request: Request):
    """
    Test endpoint
    """
    return "API is working!"


@router.get("/keepalive")
@version(1)
def hello_world(request: Request):
    """
    Keepalive endpoint
    """
    return "Yup, I'm alive!"


@router.post("/login")
@version(1)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        form_data (Annotated[OAuth2PasswordRequestForm, Depends): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Returns:
        _type_: _description_
    """
    return await login_for_access_token(form_data, db)


@router.post(
    "/signup",
    response_model=schemas.User,
    # responses={
    #     200: {"model": schemas.User},
    #     400: {"model": schemas.HttpException},
    #     "default": {"model": schemas.HttpException},
    # },
)
@version(1)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register new user

    Password requirements:
    - Length must be between 12 and 24 characters
    - 1 Uppercase letter
    - 1 Lowercase letter
    - 1 Number
    - 1 Special character
    """
    if user.invitation_key != config.INVITATION_KEY:
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.INVALID_INVITATION_KEY
            ).to_json(),
        )
    db_user = users.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.USER_ALREADY_EXISTS
            ).to_json(),
        )
    validation, new_user = users.create_user(db=db, user=user)
    if not validation:
        if new_user == 0:
            raise HTTPException(
                status_code=400,
                detail=CustomExceptions(
                    CustomExceptions.SignUp.PASSWORD_REQUIREMENTS
                ).to_json(),
            )
        if new_user == 1:
            raise HTTPException(
                status_code=400,
                detail=CustomExceptions(
                    CustomExceptions.SignUp.EMAIL_VALIDATION
                ).to_json(),
            )
    user_added = users.get_user_by_username(db, user.username)
    return user_added


@router.post("/token", response_model=auth.Token)
@version(1)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """_summary_

    Args:
        form_data (Annotated[OAuth2PasswordRequestForm, Depends): _description_
        db (Session, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        _type_: _description_
    """
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=int(config.ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = auth.create_access_token(
        data={
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "telegram_id": user.telegram_id,
            "clockify_id": user.clockify_id,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
        },
        expires_delta=access_token_expires,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/auth/active_user", response_model=schemas.User)
@version(1)
def active_user(user: models.User = Security(auth.get_current_active_user)):
    """
    Get active user info
    """
    """_summary_

    Returns:
        _type_: _description_
    """
    return user


@router.post("/wABU7qR5s3AUuvKZcdPT3FsK7rSp5EQZ", include_in_schema=False)
@version(1)
async def debugging_purposes(request: Request):
    data = await request.json()
    # logger.debug("Timer updated: " + str(data["user"]))
    # logger.info(len(data))
    # logger.info("Received data: " + str(await request.json()))
    return {"message": "Done"}
