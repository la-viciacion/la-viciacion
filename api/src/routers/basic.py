import hmac
import ipaddress
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_versioning import version
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..config import Config
from ..crud import users
from ..database import models, schemas
from ..utils import actions as actions
from ..utils import messages as msg
from ..utils import my_utils as utils
from ..utils.custom_exceptions import CustomExceptions
from ..utils.logger import LogManager
from ..utils.rate_limit import AttemptLimiter

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

# Failed attempts: per account name (guessing one password), per client (spraying)
# and for wrong invitation keys. Blocked callers get a 429 until the window passes.
LOGIN_BY_ACCOUNT = AttemptLimiter(max_failures=5, window_seconds=15 * 60)
LOGIN_BY_CLIENT = AttemptLimiter(max_failures=40, window_seconds=15 * 60)
SIGNUP_KEY = AttemptLimiter(max_failures=10, window_seconds=15 * 60)


def client_key(host: str | None) -> str | None:
    """Address to count failed logins against, or None when it says nothing about the caller.

    Behind the nginx proxy the peer is a container on the private network, the same for
    everybody: counting it would let anyone lock all the others out. A real client
    address only shows up when uvicorn is told which proxies to trust (FORWARDED_ALLOW_IPS).
    """
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return None
    return None if address.is_private or address.is_loopback else host


def _client(request: Request) -> str | None:
    return client_key(request.client.host if request.client else None)


def _block_if_limited(*retry_after_seconds: int) -> None:
    wait = max(retry_after_seconds)
    if wait > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=msg.TOO_MANY_ATTEMPTS.format(minutes=-(-wait // 60)),
            headers={"Retry-After": str(wait)},
        )

router = APIRouter(
    tags=["Basic"],
    responses={404: {"description": "Not found"}},
)


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
def signup(request: Request, user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Register new user

    Password requirements:
    - Length must be between 12 and 24 characters
    - 1 Uppercase letter
    - 1 Lowercase letter
    - 1 Number
    - 1 Special character
    """
    _block_if_limited(SIGNUP_KEY.retry_after("signup"))
    if not hmac.compare_digest(user.invitation_key.encode(), config.INVITATION_KEY.encode()):
        SIGNUP_KEY.fail("signup")
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.INVALID_INVITATION_KEY
            ).to_json(),
        )
    user.email = utils.normalize_email(user.email) or ""
    username_error = utils.validate_username(user.username)
    if username_error:
        raise HTTPException(status_code=400, detail=username_error)
    db_user = users.get_user_by_username(db, username=user.username)
    if db_user:
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.USER_ALREADY_EXISTS
            ).to_json(),
        )
    if users.email_in_use(db, user.email):
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.EMAIL_ALREADY_EXISTS
            ).to_json(),
        )
    if not utils.validate_email_format(user.email):
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(CustomExceptions.SignUp.EMAIL_VALIDATION).to_json(),
        )
    if not utils.validate_password_requirements(user.password):
        raise HTTPException(
            status_code=400,
            detail=CustomExceptions(
                CustomExceptions.SignUp.PASSWORD_REQUIREMENTS
            ).to_json(),
        )
    # whoever holds the invitation key gets an active account straight away
    return users.insert_user(
        db,
        username=user.username,
        email=user.email,
        name=user.name,
        password=user.password,
        is_active=True,
    )


@router.post("/token", response_model=auth.Token)
@version(1)
async def login_for_access_token(
    request: Request,
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
    account = form_data.username.strip().lower()[:255]
    client = _client(request)
    _block_if_limited(
        LOGIN_BY_ACCOUNT.retry_after(account), LOGIN_BY_CLIENT.retry_after(client) if client else 0
    )
    user = auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        LOGIN_BY_ACCOUNT.fail(account)
        if client:
            LOGIN_BY_CLIENT.fail(client)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    LOGIN_BY_ACCOUNT.reset(account)
    if not user.is_active:
        # only after a correct password, so this does not reveal which accounts exist
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg.ACCOUNT_DISABLED)
    access_token_expires = timedelta(minutes=int(config.ACCESS_TOKEN_EXPIRE_MINUTES))
    access_token = auth.create_access_token(
        data={
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "telegram_id": user.telegram_id,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "pwv": auth.password_fingerprint(user),
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
