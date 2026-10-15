"""Notices written by an admin: by push to the app's devices or by Telegram."""
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...database import models
from ...utils import my_utils, push, settings
from ...utils.logger import LogManager
from .common import get_or_404, router

logger = LogManager().get_logger()


class AnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=push.TITLE_MAX)
    body: Optional[str] = Field(None, max_length=push.ANNOUNCEMENT_BODY_MAX)
    url: Optional[str] = Field(None, max_length=200)
    image: Optional[str] = Field(None, max_length=500)
    audience: str = Field("me", pattern="^(me|user|group|all)$")
    user_id: Optional[int] = None


@router.get("/push/audience")
def push_audience(db: Session = Depends(get_db)):
    """Who can receive a notice, by channel (for the composer): the devices of the app by audience, and
    whether Telegram has a bot and a group."""
    q = db.query(models.PushSubscription)
    return {
        "ready": push.is_ready(),
        "telegram": {"ready": bool(settings.get("telegram.token")), "group": bool(settings.get("telegram.group_id"))},
        "all": {"devices": q.count(), "users": q.with_entities(func.count(func.distinct(models.PushSubscription.user_id))).scalar()},
        "group": {
            "devices": q.filter(models.PushSubscription.receive_group == True).count(),  # noqa: E712
            "users": q.filter(models.PushSubscription.receive_group == True)  # noqa: E712
            .with_entities(func.count(func.distinct(models.PushSubscription.user_id)))
            .scalar(),
        },
        "users": {
            user_id: devices
            for user_id, devices in q.with_entities(models.PushSubscription.user_id, func.count(models.PushSubscription.id))
            .group_by(models.PushSubscription.user_id)
            .all()
        },
    }


@router.post("/push/announce")
async def send_announcement(
    body: AnnouncementBody,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Send a notice written by an admin to their own devices ("me"), one user's, the group ones or everybody's."""
    if not push.is_ready():
        raise HTTPException(status_code=409, detail="Los avisos push no están listos: revisa que estén activados")
    try:
        payload = push.build_announcement(body.title, body.body, body.url, body.image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    user_id = admin.id
    if body.audience == "user":
        if body.user_id is None:
            raise HTTPException(status_code=400, detail="Falta elegir el usuario")
        user_id = get_or_404(db, models.User, body.user_id, "Usuario").id
    sent, failed = await push.deliver(payload, body.audience, user_id)
    logger.info(f"Announcement by {admin.username} to {body.audience}: {sent} sent, {failed} failed")
    if sent == 0:
        detail = "Ningún dispositivo lo ha aceptado" if failed else "No hay ningún dispositivo suscrito en ese destino"
        raise HTTPException(status_code=404, detail=detail)
    return {"sent": sent, "failed": failed}


class TelegramAnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=push.TITLE_MAX)
    body: Optional[str] = Field(None, max_length=push.ANNOUNCEMENT_BODY_MAX)
    audience: str = Field("me", pattern="^(me|user|group)$")
    user_id: Optional[int] = None


@router.post("/telegram/announce")
async def send_telegram_announcement(
    body: TelegramAnnouncementBody,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Send a notice written by an admin by Telegram only: to their own private chat ("me"), one user's or the
    group's. The app's devices get nothing (see /push/announce for those)."""
    if not settings.get("telegram.token"):
        raise HTTPException(status_code=409, detail="Telegram no está configurado: falta el token del bot")
    if body.audience == "group":
        chat_id, who = settings.get("telegram.group_id"), "el grupo"
        if not chat_id:
            raise HTTPException(status_code=409, detail="Falta el ID del grupo de Telegram")
    else:
        target = admin
        if body.audience == "user":
            if body.user_id is None:
                raise HTTPException(status_code=400, detail="Falta elegir el usuario")
            target = get_or_404(db, models.User, body.user_id, "Usuario")
        chat_id, who = target.telegram_id, target.username
        if chat_id is None:
            raise HTTPException(status_code=409, detail=f"{target.username} no tiene Telegram ID")
    if not await my_utils.send_announcement_to_chat(chat_id, body.title, body.body):
        raise HTTPException(status_code=502, detail="Telegram no ha aceptado el mensaje")
    logger.info(f"Telegram announcement by {admin.username} to {body.audience}")
    return {"message": f"Enviado a {who}"}
