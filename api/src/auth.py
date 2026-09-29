from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery, OAuth2PasswordBearer

import jwt

from pydantic import BaseModel
import bcrypt
from sqlalchemy.orm import Session

from .config import Config
from .crud import users
from .database import models
from .database.database import SessionLocal
from .utils import messages

config = Config()
ALGORITHM = "HS256"


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


def verify_password(plain_password: str, hashed_password: str):
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str):
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed_password


def authenticate_user(db, login: str, password: str):
    """`login` is a username or an email."""
    user = users.get_user_by_login(db, login)
    if not user:
        return False
    if not verify_password(password, user.password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("username")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except Exception:
        raise credentials_exception
    user = users.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


def require_admin(
    current_user: Annotated[models.User, Depends(get_current_active_user)]
):
    """Dependency: only admins get through."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=messages.USER_NOT_ADMIN
        )
    return current_user


def ensure_self_or_admin(
    current_user: models.User, user_id: int | None = None, username: str | None = None
):
    """Only the owner of the data (by id or username) or an admin may touch it."""
    if current_user.is_admin:
        return
    if (user_id is not None and current_user.id == user_id) or (
        username is not None and current_user.username == username
    ):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=messages.USER_NOT_ADMIN
    )


def get_api_key(
    api_key_header: str = Security(api_key_header),
) -> str:
    if api_key_header == config.API_KEY:
        return api_key_header
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
    )
