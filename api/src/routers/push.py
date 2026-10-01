"""Push subscriptions of the installed PWA (see utils/push.py)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi_versioning import version
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import users as users_crud
from ..database import models
from ..utils import actions, push, settings
from . import timers

# No router-wide login: /stop-timer is the one route here that authenticates with its own token.
# Every other route asks for the session explicitly (test_endpoint_security.py checks it).
router = APIRouter(prefix="/push", tags=["Push"])


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


class StopTimerBody(BaseModel):
    token: str = Field(min_length=1, max_length=1000)


@router.post("/stop-timer")
@version(1)
def stop_timer_from_notification(
    body: StopTimerBody,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """The "Parar" button of the running-timer notification. Open to anyone holding the signed token
    the notification carries (the service worker has no session): it only stops that one timer, for
    15 minutes at most. Stopping an already stopped timer is not an error."""
    try:
        user_id, timer_id = push.read_stop_token(body.token)
    except ValueError:
        raise HTTPException(status_code=401, detail="El botón de la notificación ha caducado, abre la app para parar el timer")
    user = users_crud.get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="El botón de la notificación ha caducado, abre la app para parar el timer")
    ranking_before = actions.ranking_snapshot(db)
    try:
        timer = timers.stop_timer(db, timer_id, user_id)
    except HTTPException:
        return {"stopped": False}
    background_tasks.add_task(actions.after_session_change, user_id, False, ranking_before)
    background_tasks.add_task(actions.after_timer_stop, user_id, timer.game_id, timer.duration_seconds)
    return {"stopped": True}
