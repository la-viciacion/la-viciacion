"""Notices written by an admin: by push to the app's devices or by Telegram."""
import datetime
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...crud import recap
from ...database import models
from ...utils import actions, messages, my_utils, push, recap_notices, settings
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


def _recap_period(text: str) -> recap.Period:
    try:
        period = recap.parse_period(text)
    except ValueError:
        raise HTTPException(status_code=400, detail=messages.RECAP_PERIOD_INVALID)
    if period.start > datetime.date.today():
        raise HTTPException(status_code=400, detail=messages.RECAP_PERIOD_FUTURE)
    return period


@router.get("/recap/preview")
def recap_preview(period: str, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    """The texts the recap of a month or a season would send, without sending anything: the group's and, with
    `user_id`, that player's. The AI is not asked: the group's goes out rewritten only when it is on for this notice."""
    parsed = _recap_period(period)
    if user_id is not None:
        get_or_404(db, models.User, user_id, "Usuario")
    data = recap.build_recap(db, parsed, user_id)
    return {
        "period": parsed.key,
        "label": recap_notices.period_label(parsed),
        "group_message": recap_notices.group_message(data, parsed),
        "player_message": recap_notices.player_message(data, parsed) if user_id is not None else None,
        "nobody_played": data["group"]["seconds"] == 0,
    }


class RecapSendBody(BaseModel):
    period: str
    audience: str = Field("me", pattern="^(me|group|all)$")


@router.post("/recap/send")
async def recap_send(
    body: RecapSendBody,
    admin: models.User = Depends(auth.require_admin),
    db: Session = Depends(get_db),
):
    """Send a recap now, as the monthly job would: to the admin alone ("me", their private one), to the group
    (the group's one only) or to everybody ("all": the group's and each player's own)."""
    parsed = _recap_period(body.period)
    if admin.telegram_id is None and body.audience == "me" and not actions.push_has_devices(admin.id):
        raise HTTPException(status_code=409, detail="No tienes Telegram ID ni dispositivos con avisos para recibir la prueba")
    result = await recap_notices.announce_recap(
        db, parsed, group=body.audience in ("group", "all"), players=body.audience in ("me", "all"), only=admin if body.audience == "me" else None
    )
    if result["empty"]:
        raise HTTPException(status_code=409, detail="Nadie jugó en ese periodo: no hay nada que enviar")
    logger.info(f"Recap {parsed.key} sent by {admin.username} to {body.audience}: {recap_notices.describe(result)}")
    return {"message": recap_notices.describe(result), **result}
