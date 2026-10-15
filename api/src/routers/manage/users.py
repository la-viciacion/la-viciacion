"""Accounts: list, create, edit, password and delete."""
from typing import Optional

from bcrypt import gensalt, hashpw
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...crud import users as users_crud
from ...database import models
from ...utils.my_utils import normalize_email, validate_email_format, validate_password_requirements, validate_username
from .common import commit, confirm_or_409, get_or_404, like, router


def _user_out(u: models.User, sessions: int = 0, library: int = 0) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "username": u.username,
        "email": u.email,
        "telegram_id": u.telegram_id,
        "is_admin": bool(u.is_admin),
        "is_active": bool(u.is_active),
        "sessions": sessions,
        "library": library,
    }


@router.get("/users")
def list_users(
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(models.User)
    if search:
        t = like(search)
        q = q.filter(or_(models.User.username.like(t), models.User.name.like(t), models.User.email.like(t)))
    total = q.count()
    users = q.order_by(models.User.username).limit(limit).offset(offset).all()
    ids = [u.id for u in users]
    sessions = dict(
        db.query(models.GameTimer.user_id, func.count(models.GameTimer.id))
        .filter(models.GameTimer.user_id.in_(ids))
        .group_by(models.GameTimer.user_id)
        .all()
    )
    library = dict(
        db.query(models.UserGame.user_id, func.count(models.UserGame.id))
        .filter(models.UserGame.user_id.in_(ids))
        .group_by(models.UserGame.user_id)
        .all()
    )
    return {"total": total, "items": [_user_out(u, sessions.get(u.id, 0), library.get(u.id, 0)) for u in users]}


def _checked_email(db: Session, email, *, exclude_user_id=None):
    """Normalized email that is valid and free: it is the login identifier, so it is required."""
    email = normalize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="El email es obligatorio")
    if not validate_email_format(email):
        raise HTTPException(status_code=400, detail="El email no es válido")
    if users_crud.email_in_use(db, email, exclude_user_id=exclude_user_id):
        raise HTTPException(status_code=409, detail="Ese email ya está en uso por otra cuenta")
    return email


def _check_username(db: Session, username: str, *, exclude_user_id=None):
    error = validate_username(username)
    if error:
        raise HTTPException(status_code=400, detail=error)
    other = users_crud.get_user_by_username(db, username)
    if other and other.id != exclude_user_id:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe")


def _check_telegram_id(db: Session, telegram_id, *, exclude_user_id=None):
    if telegram_id is not None and users_crud.telegram_id_in_use(db, telegram_id, exclude_user_id=exclude_user_id):
        raise HTTPException(status_code=409, detail="Ese ID de Telegram ya está en uso por otra cuenta")


class UserCreateBody(BaseModel):
    email: str
    username: str
    name: Optional[str] = None
    telegram_id: Optional[int] = None
    password: str
    is_admin: bool = False
    is_active: bool = True


@router.post("/users", status_code=201)
def create_user(body: UserCreateBody, db: Session = Depends(get_db)):
    """Create an account (the only way to add users for now)."""
    email = _checked_email(db, body.email)
    username = body.username.strip()
    _check_username(db, username)
    _check_telegram_id(db, body.telegram_id)
    if not validate_password_requirements(body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener 12-24 caracteres, mayúscula, minúscula, número y un carácter especial",
        )
    try:
        user = users_crud.insert_user(
            db,
            username=username,
            email=email,
            name=(body.name or "").strip() or None,
            password=body.password,
            is_admin=body.is_admin,
            is_active=body.is_active,
            telegram_id=body.telegram_id,
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Ese email o usuario ya existe")
    return _user_out(user)


class UserPatch(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int,
    body: UserPatch,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = get_or_404(db, models.User, user_id, "Usuario")
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and (data.get("is_admin") is False or data.get("is_active") is False):
        raise HTTPException(status_code=400, detail="No puedes quitarte el rol de admin ni desactivarte a ti mismo")
    if data.get("telegram_id") is not None:
        _check_telegram_id(db, data["telegram_id"], exclude_user_id=user.id)
    if "name" in data:
        # never empty: messages and rankings print it (falls back to the nickname)
        data["name"] = (data["name"] or "").strip() or (data.get("username") or user.username).strip()
    if "email" in data:
        data["email"] = _checked_email(db, data["email"], exclude_user_id=user.id)
    if data.get("username") is not None:
        data["username"] = data["username"].strip()
        _check_username(db, data["username"], exclude_user_id=user.id)
    for field in ("is_admin", "is_active"):
        if field in data and data[field] is not None:
            data[field] = int(data[field])
    for k, v in data.items():
        setattr(user, k, v)
    commit(db, "Usuario")
    return _user_out(user)


class PasswordBody(BaseModel):
    password: str


@router.post("/users/{user_id}/password")
def set_password(user_id: int, body: PasswordBody, db: Session = Depends(get_db)):
    user = get_or_404(db, models.User, user_id, "Usuario")
    if not validate_password_requirements(body.password):
        raise HTTPException(
            status_code=400,
            detail="La contraseña debe tener 12-24 caracteres, mayúscula, minúscula, número y un carácter especial",
        )
    user.password = hashpw(body.password.encode("utf-8"), gensalt()).decode()
    db.commit()
    return {"message": "Contraseña actualizada"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    force: bool = False,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    user = get_or_404(db, models.User, user_id, "Usuario")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes borrarte a ti mismo")
    counts = {
        "sesiones": db.query(models.GameTimer).filter_by(user_id=user_id).count(),
        "biblioteca": db.query(models.UserGame).filter_by(user_id=user_id).count(),
        "logros": db.query(models.UserAchievement).filter_by(user_id=user_id).count(),
        "puntuaciones": db.query(models.GameScore).filter_by(user_id=user_id).count(),
        "deseados": db.query(models.UserWishlist).filter_by(user_id=user_id).count(),
    }
    confirm_or_409(counts, force)
    db.query(models.GameTimer).filter_by(user_id=user_id).delete()
    db.query(models.UserGame).filter_by(user_id=user_id).delete()
    db.query(models.GameScore).filter_by(user_id=user_id).delete()
    db.query(models.UserWishlist).filter_by(user_id=user_id).delete()
    db.query(models.UserAchievement).filter_by(user_id=user_id).delete()
    db.query(models.PushSubscription).filter_by(user_id=user_id).delete()
    db.delete(user)
    db.commit()
    return {"message": "Usuario eliminado"}
