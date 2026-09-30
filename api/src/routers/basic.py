import ipaddress
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Security, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_versioning import version
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..config import Config
from ..crud import users
from ..database import models, schemas
from ..utils import messages as msg
from ..utils import password_reset
from ..utils.my_utils import validate_password_requirements
from ..utils.logger import LogManager
from ..utils.rate_limit import AttemptLimiter

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()

# Failed logins: per account name (guessing one password) and per client (spraying).
# Blocked callers get a 429 until the window passes.
LOGIN_BY_ACCOUNT = AttemptLimiter(max_failures=5, window_seconds=15 * 60)
LOGIN_BY_CLIENT = AttemptLimiter(max_failures=40, window_seconds=15 * 60)
# Password recovery: every request for a link counts (found or not, so the count says nothing about
# which accounts exist): 3 links per account and hour, 20 requests per client and hour; and wrong or
# stale links per client.
RECOVERY_BY_ACCOUNT = AttemptLimiter(max_failures=3, window_seconds=60 * 60)
RECOVERY_BY_CLIENT = AttemptLimiter(max_failures=20, window_seconds=60 * 60)
RESET_LINK_FAILS = AttemptLimiter(max_failures=20, window_seconds=15 * 60)


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
def keepalive(request: Request):
    """
    Keepalive endpoint
    """
    return "Yup, I'm alive!"


@router.post("/token", response_model=auth.Token)
@version(1)
def login_for_access_token(
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


class ForgotPasswordBody(BaseModel):
    login: str = Field(min_length=1, max_length=255)  # username or email


class ResetPasswordBody(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/auth/forgot-password", status_code=202)
@version(1)
def forgot_password(
    request: Request,
    body: ForgotPasswordBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Email a one-time link to choose a new password.

    The answer is the same whether the account exists or not (no way to probe which users or emails
    are registered); the email goes to the address stored on the account, never to the one typed."""
    if not config.MAIL_ENABLED:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=msg.RECOVERY_NOT_CONFIGURED)
    client = _client(request)
    _block_if_limited(RECOVERY_BY_CLIENT.retry_after(client) if client else 0)
    if client:
        RECOVERY_BY_CLIENT.fail(client)
    user = users.get_user_by_login(db, body.login)
    if user and user.is_active and user.email and RECOVERY_BY_ACCOUNT.retry_after(str(user.id)) == 0:
        RECOVERY_BY_ACCOUNT.fail(str(user.id))
        token = password_reset.create_token(db, user)
        background_tasks.add_task(password_reset.send_recovery_email, user.email, user.name, token)
    return {"message": msg.RECOVERY_REQUESTED}


@router.post("/auth/reset-password")
@version(1)
def reset_password(request: Request, body: ResetPasswordBody, db: Session = Depends(get_db)):
    """Choose a new password with the link sent by email. It also signs out every session."""
    client = _client(request)
    _block_if_limited(RESET_LINK_FAILS.retry_after(client) if client else 0)
    # the rules first: a weak password must not use up the link
    if not validate_password_requirements(body.new_password):
        raise HTTPException(status_code=400, detail=msg.PASSWORD_RULES)
    if not password_reset.reset_password(db, body.token, body.new_password):
        if client:
            RESET_LINK_FAILS.fail(client)
        raise HTTPException(status_code=400, detail=msg.RECOVERY_LINK_INVALID)
    return {"message": msg.PASSWORD_RESET_DONE}
