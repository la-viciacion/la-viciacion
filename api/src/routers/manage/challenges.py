"""The group's challenges: launched and deleted only here."""
import datetime
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...crud import challenges as challenges_crud
from ...database import models
from ...utils import actions
from ...utils import challenges as challenges_utils
from .common import get_or_404, router


@router.get("/challenges")
def list_challenges(db: Session = Depends(get_db)):
    """Every challenge, the latest period first, with how many take part and whether the total is reached."""
    today = datetime.date.today()
    rows = []
    for challenge in db.query(models.Challenge).order_by(models.Challenge.starts_on.desc(), models.Challenge.id.desc()):
        shown = challenges_crud.view(db, challenge, 0, today)
        owner = db.get(models.User, challenge.created_by) if challenge.created_by else None
        rows.append({
            "id": challenge.id, "title": shown["title"], "label": shown["label"], "scope": shown["scope"], "status": shown["status"],
            "starts_on": challenge.starts_on, "ends_on": challenge.ends_on, "visibility": challenge.visibility,
            "created_by": owner.username if owner else None,
            "owner": shown["owner"]["name"] if shown["owner"] else None,
            "players": len(shown["progress"]["players"]),
            "done_players": sum(1 for p in shown["progress"]["players"] if p["done"]),
            "total_done": shown["progress"].get("total_done"),
            "notified": challenge.total_notified_at is not None,
        })
    return rows


@router.get("/challenges/tags")
def list_challenge_tags(db: Session = Depends(get_db)):
    """The tags a themed challenge can be about: those of the games in the database, with how many games have each."""
    return [{"tag": name, "games": count} for _, (name, count) in sorted(challenges_utils.available_tags(db).items())]


class NewGroupChallenge(BaseModel):
    kind: str = "game_of_month"
    # the options of the templates, flat (the panel's form posts them as they are); each template reads its own
    game_id: Optional[str] = None
    month: Optional[str] = None
    min_hours_each: Optional[float] = None
    min_hours_total: Optional[float] = None
    tag: Optional[str] = None
    mode: Optional[str] = None
    min_games_total: Optional[int] = None
    announce: bool = True  # tell the group (Telegram and push) that it was launched


@router.post("/challenges", status_code=201)
def launch_group_challenge(body: NewGroupChallenge, background_tasks: BackgroundTasks, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Launch a challenge for the whole group. They are the app's, so only here (the audit log records who) and
    never from the challenges page, where players launch their own."""
    template = challenges_utils.TEMPLATES.get(body.kind)
    if template is None or template.scope != challenges_utils.GROUP:
        raise HTTPException(status_code=400, detail="Ese tipo de reto de grupo no existe")
    options = body.model_dump(exclude={"kind", "announce"}, exclude_none=True)
    today = datetime.date.today()
    try:
        challenge = challenges_crud.create(db, admin, body.kind, options, today)
    except challenges_utils.ChallengeError as e:
        raise HTTPException(status_code=409 if "Ya existe" in str(e) else 400, detail=str(e))
    if body.announce:
        background_tasks.add_task(actions.after_challenge_launch, challenge.id)
    return challenges_crud.view(db, challenge, admin.id, today)


@router.delete("/challenges/{challenge_id}")
def delete_challenge(challenge_id: int, db: Session = Depends(get_db)):
    """Delete a challenge (its opt-outs go with it)."""
    challenges_crud.delete(db, get_or_404(db, models.Challenge, challenge_id, "Reto"))
    return {"message": "Reto eliminado"}
