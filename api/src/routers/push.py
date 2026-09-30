"""Push subscriptions of the installed PWA (see utils/push.py)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi_versioning import version
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..database import models
from ..utils import push, settings

router = APIRouter(
    prefix="/push",
    tags=["Push"],
    dependencies=[Depends(auth.get_current_active_user)],
)


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=700, pattern="^https://")
    keys: Keys
    receive_group: bool = True
    user_agent: str | None = Field(default=None, max_length=255)


class EndpointBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=700)


class PreferenceBody(EndpointBody):
    receive_group: bool


@router.get("/config")
@version(1)
def get_config(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Whether push is available and the public key the browser needs, plus the caller's devices."""
    devices = db.query(models.PushSubscription).filter_by(user_id=current_user.id).all()
    ready = push.is_ready()
    return {
        "enabled": ready,
        "public_key": settings.get("push.vapid_public") if ready else None,
        "devices": [
            {
                "endpoint": d.endpoint,
                "receive_group": bool(d.receive_group),
                "user_agent": d.user_agent,
                "created_at": d.created_at,
            }
            for d in devices
        ],
    }


@router.post("/subscribe")
@version(1)
def subscribe(
    body: SubscribeBody,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Register (or refresh) this device for the caller. A device that changes account moves to it."""
    if not push.is_ready():
        raise HTTPException(status_code=409, detail="Las notificaciones push no están activadas")
    row = db.query(models.PushSubscription).filter_by(endpoint=body.endpoint).first()
    if row is None:
        row = models.PushSubscription(endpoint=body.endpoint)
        db.add(row)
    row.user_id = current_user.id
    row.p256dh = body.keys.p256dh
    row.auth = body.keys.auth
    row.receive_group = body.receive_group
    row.user_agent = body.user_agent
    db.flush()
    # keep the newest devices only
    owned = (
        db.query(models.PushSubscription)
        .filter_by(user_id=current_user.id)
        .order_by(models.PushSubscription.id.desc())
        .all()
    )
    for old in owned[push.MAX_DEVICES_PER_USER:]:
        db.delete(old)
    db.commit()
    return {"message": "Dispositivo registrado"}


@router.post("/unsubscribe")
@version(1)
def unsubscribe(
    body: EndpointBody,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    db.query(models.PushSubscription).filter_by(endpoint=body.endpoint, user_id=current_user.id).delete()
    db.commit()
    return {"message": "Dispositivo eliminado"}


@router.patch("/subscription")
@version(1)
def set_preference(
    body: PreferenceBody,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Choose whether this device also gets the group notices (the private ones always arrive)."""
    row = db.query(models.PushSubscription).filter_by(endpoint=body.endpoint, user_id=current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    row.receive_group = body.receive_group
    db.commit()
    return {"receive_group": bool(row.receive_group)}
