"""Settings, diagnostics (Telegram, AI, mail), the backup and the audit log."""
import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...database import models
from ...utils import ai, audit, my_utils, push, settings, sql_dump
from ...utils import email as mail
from ...utils.logger import LogManager
from .common import router

logger = LogManager().get_logger()


# ── Settings and their diagnostics ──────────────────────────────


@router.get("/settings")
def get_settings(admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Settings for the admin panel (the Telegram token is never returned, only whether it is set)."""
    jobs = {j.job: {"last_run_at": j.last_run_at, "last_status": j.last_status} for j in db.query(models.JobRun).all()}
    push_devices = {
        "devices": db.query(func.count(models.PushSubscription.id)).scalar(),
        "users": db.query(func.count(func.distinct(models.PushSubscription.user_id))).scalar(),
    }
    # mail comes from the environment, not from app_settings: shown read-only, with where a test goes
    mail_info = {**mail.status(), "test_recipient": admin.email}
    return {
        "values": settings.public_view(db),
        "jobs": jobs,
        "push_devices": push_devices,
        "mail": mail_info,
        "ai_uses": settings.ai_uses(db),
        "ai_model": ai.in_use(),
    }


class SettingsBody(BaseModel):
    values: dict


@router.put("/settings")
def put_settings(body: SettingsBody, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Change several settings at once; nothing is stored if one of them is invalid."""
    if any(key.startswith("push.vapid") for key in body.values):
        raise HTTPException(status_code=400, detail="Las claves VAPID se generan con «Generar claves», no se escriben")
    if any(settings.REGISTRY[key].env_only for key in body.values if key in settings.REGISTRY):
        raise HTTPException(status_code=400, detail="El token y los IDs de Telegram y la clave de la IA se configuran en el .env del servidor, no desde el panel")
    try:
        changed = settings.set_values(db, body.values, user_id=admin.id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    return {"changed": changed, "values": settings.public_view(db)}


@router.post("/settings/push-keys")
def generate_push_keys(replace: bool = False, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Generate the VAPID keys for Web Push. Replacing existing keys invalidates every subscribed device."""
    current = settings.get_all(db)
    if current["push.vapid_private"] and not replace:
        raise HTTPException(status_code=409, detail="Ya hay claves; reemplazarlas obliga a todos a volver a activar los avisos")
    public, private = push.generate_vapid_keys()
    settings.set_values(db, {"push.vapid_public": public, "push.vapid_private": private}, user_id=admin.id)
    if replace:
        db.query(models.PushSubscription).delete()
        db.commit()
    return {"public_key": public}


@router.post("/settings/test-message")
async def send_test_message(admin: models.User = Depends(auth.require_admin)):
    """Send a diagnostic message to the configured group."""
    try:
        await my_utils.send_test_message(admin.username)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Telegram no lo ha aceptado: {e}")
    return {"message": "Mensaje enviado"}


@router.post("/settings/test-ai")
def test_ai(admin: models.User = Depends(auth.require_admin)):
    """Ask the AI for one short sentence with the provider, model and key of the environment (blocking network call:
    a plain def, so it runs in a worker thread). Works with the AI switched off, to try a key before using it."""
    if not settings.get("ai.api_key"):
        raise HTTPException(status_code=409, detail="No hay ninguna clave de IA: falta AI_API_KEY en el .env del servidor")
    provider, model = ai.current()
    if provider not in ai.PROVIDERS or not model:
        raise HTTPException(
            status_code=409,
            detail="La IA no está completa: AI_PROVIDER (" + " o ".join(ai.PROVIDERS) + ") y AI_MODEL deben estar en el .env del servidor",
        )
    try:
        reply = ai.complete(
            "Responde solo con una frase corta y divertida sobre videojuegos.", "Saluda al grupo.", force=True
        )
    except ai.AIError as e:
        logger.error(f"AI test by {admin.username} failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"La IA no ha respondido: {e}")
    return {"message": "La IA ha respondido", "reply": reply, "provider": provider, "model": model}


@router.post("/settings/test-email")
def send_test_email(admin: models.User = Depends(auth.require_admin)):
    """Send a diagnostic email to the email of the admin who asks (blocking SMTP: a plain def, so it
    runs in a worker thread). Tells why when it cannot."""
    missing = mail.missing_settings()
    if missing:
        raise HTTPException(status_code=409, detail="El correo no está configurado: faltan " + ", ".join(missing) + " en el .env")
    if not admin.email:
        raise HTTPException(status_code=400, detail="Tu cuenta no tiene email: añádelo en Usuarios → Editar")
    try:
        mail.send_test_email(admin.email, admin.username)
    except Exception as e:
        logger.error(f"Test email failed: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"El servidor de correo no lo ha aceptado: {e}")
    return {"message": f"Correo de prueba enviado a {admin.email}"}


# ── Backup ──────────────────────────────────────────────────────


@router.post("/backup")
def download_backup(db: Session = Depends(get_db)):
    """The whole database as a gzipped `.sql` file (see utils/sql_dump.py). It is a POST although it only reads, so the
    audit log records who took a copy of everything and a link or a prefetch cannot trigger it."""
    name = f"laviciacion-backup-{datetime.date.today()}.sql.gz"
    return StreamingResponse(
        sql_dump.gzip_stream(sql_dump.dump(db.get_bind())),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


# ── Audit log ───────────────────────────────────────────────────


@router.get("/audit")
def list_audit(
    user_id: Optional[int] = None,
    entity: Optional[str] = Query(None, max_length=50),
    method: Optional[str] = Query(None, pattern="^(POST|PUT|PATCH|DELETE)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """What the admins changed, newest first."""
    q = db.query(models.AuditLog)
    if user_id is not None:
        q = q.filter(models.AuditLog.user_id == user_id)
    if entity:
        q = q.filter(models.AuditLog.entity == entity)
    if method:
        q = q.filter(models.AuditLog.method == method)
    total = q.count()
    rows = q.order_by(models.AuditLog.id.desc()).limit(limit).offset(offset).all()
    return {"total": total, "items": [audit.entry_out(r) for r in rows]}
