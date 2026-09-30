"""Password recovery: a one-time link sent by email.

The flow: the user asks for a link (`create_token`), the API emails it (`send_recovery_email`),
the user opens it and chooses a new password (`reset_password`).

- The token is 256 random bits; only its SHA-256 is stored, so a copy of the database cannot be
  used to take over an account.
- It is valid for one hour and for one use. Asking again invalidates the previous link.
- Using it changes the password hash, which also signs out every session of that user
  (`auth.password_fingerprint` travels inside the tokens).
"""
import datetime
import hashlib
import html
import secrets

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import Config
from ..crud import users
from ..database import models
from . import email
from .logger import LogManager

logger = LogManager().get_logger()
config = Config()

TOKEN_VALID_FOR = datetime.timedelta(hours=1)
KEEP_SPENT_FOR = datetime.timedelta(days=1)  # used or expired rows are removed after this


def _now() -> datetime.datetime:
    """UTC, naive (what the columns hold): a daylight-saving change must not stretch the hour."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(db: Session, user: models.User) -> str:
    """A new recovery token for the user (returned once, never stored as is). Their earlier
    unused links stop working, and old spent rows are tidied up."""
    now = _now()
    db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id, models.PasswordReset.used_at.is_(None)
    ).delete(synchronize_session=False)
    db.query(models.PasswordReset).filter(models.PasswordReset.expires_at < now - KEEP_SPENT_FOR).delete(
        synchronize_session=False
    )
    token = secrets.token_urlsafe(32)
    db.add(
        models.PasswordReset(
            user_id=user.id, token_hash=hash_token(token), created_at=now, expires_at=now + TOKEN_VALID_FOR
        )
    )
    db.commit()
    return token


def reset_password(db: Session, token: str, new_password: str) -> bool:
    """Use the token to set a new password. False if it is unknown, expired, already used, or its
    account is disabled. Claiming the token and changing the password are one transaction, so two
    requests with the same link cannot both succeed."""
    row = db.query(models.PasswordReset).filter(models.PasswordReset.token_hash == hash_token(token)).first()
    if row is None:
        return False
    now = _now()
    claimed = db.execute(
        update(models.PasswordReset)
        .where(
            models.PasswordReset.id == row.id,
            models.PasswordReset.used_at.is_(None),
            models.PasswordReset.expires_at > now,
        )
        .values(used_at=now)
    ).rowcount
    user = db.get(models.User, row.user_id) if claimed == 1 else None
    if claimed != 1 or user is None or not user.is_active:
        db.rollback()
        return False
    user.password = users.hash_password(new_password)
    db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id, models.PasswordReset.id != row.id
    ).delete(synchronize_session=False)
    db.commit()
    logger.info(f"Password of user {user.id} changed through a recovery link")
    return True


def recovery_link(token: str) -> str:
    # in the fragment: it is never sent to a server or left in a proxy's access log
    return f"{config.PUBLIC_URL}/#/reset-password?token={token}"


def recovery_message(name: str | None, link: str) -> tuple[str, str, str]:
    """(subject, plain text, html) of the email."""
    who = (name or "").strip()
    hello = f"Hola, {who}." if who else "Hola."
    minutes = int(TOKEN_VALID_FOR.total_seconds() // 60)
    subject = "Recupera tu contraseña de La Viciación"
    text = (
        f"{hello}\n\n"
        "Alguien (esperamos que tú) ha pedido elegir una nueva contraseña para tu cuenta de La Viciación.\n"
        f"Abre este enlace para hacerlo; vale {minutes} minutos y solo se puede usar una vez:\n\n"
        f"{link}\n\n"
        "Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.\n"
    )
    safe_link = html.escape(link, quote=True)
    body = (
        f"<p>{html.escape(hello)}</p>"
        "<p>Alguien (esperamos que tú) ha pedido elegir una nueva contraseña para tu cuenta de La Viciación.</p>"
        f'<p><a href="{safe_link}">Elegir una nueva contraseña</a></p>'
        f"<p>El enlace vale {minutes} minutos y solo se puede usar una vez.</p>"
        "<p>Si no lo has pedido tú, ignora este correo: tu contraseña no cambia.</p>"
    )
    return subject, text, body


def send_recovery_email(to: str, name: str | None, token: str) -> None:
    """Background task: email the link. Never raises (there is nobody to tell) and never logs the token."""
    try:
        subject, text, body = recovery_message(name, recovery_link(token))
        email.send_email(to, subject, text, body)
        logger.info("Password recovery email sent")
    except Exception as e:
        logger.error(f"Could not send the password recovery email: {e}")
