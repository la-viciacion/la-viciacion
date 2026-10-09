import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import challenges as crud
from ..database import models
from ..utils.challenges import GROUP, TEMPLATES, ChallengeError

router = APIRouter(
    prefix="/challenges",
    tags=["Challenges"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

NOT_FOUND = "Reto no encontrado"


class NewChallenge(BaseModel):
    kind: str
    options: dict = Field(default_factory=dict)


def _challenge(db: Session, challenge_id: int, viewer: models.User) -> models.Challenge:
    """A challenge the viewer may see (every public one and their own)."""
    found = db.get(models.Challenge, challenge_id)
    if found is None or (found.visibility != "public" and found.owner_user_id != viewer.id and not viewer.is_admin):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.get("/templates")
def get_templates(current_user: models.User = Depends(auth.get_current_active_user)):
    """The kinds of challenge that exist and whether the caller may launch each one from the challenges page: only the
    personal ones. The group's are launched by an admin from the admin panel (`POST /manage/challenges`)."""
    return [
        {"kind": kind, "label": template.label, "scope": template.scope, "can_launch": template.scope != GROUP}
        for kind, template in TEMPLATES.items()
    ]


@router.get("")
def get_challenges(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every challenge the caller can see with its progress (derived; only the definition is stored)."""
    today = datetime.date.today()
    return [crud.view(db, challenge, current_user.id, today) for challenge in crud.visible(db, current_user.id)]


@router.get("/player/{player_id}")
def get_player_history(
    player_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The finished challenges a player took part in and how they did, readable by every logged-in user on purpose
    (the challenges are public), like the rest of what is public of a player."""
    if db.get(models.User, player_id) is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return crud.history(db, player_id, datetime.date.today())


@router.get("/{challenge_id}")
def get_challenge(
    challenge_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    return crud.view(db, _challenge(db, challenge_id, current_user), current_user.id, datetime.date.today())


@router.post("", status_code=201)
def launch_challenge(
    body: NewChallenge,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Launch a **personal** challenge from a template, for the caller. The group's challenges are the app's, not a
    player's: an admin launches them from the admin panel (`POST /manage/challenges`), and this refuses them for
    everybody, admins included."""
    template = TEMPLATES.get(body.kind)
    if template is None:
        raise HTTPException(status_code=400, detail="Ese tipo de reto no existe")
    if template.scope == GROUP:
        raise HTTPException(status_code=403, detail="Los retos de grupo los lanza un administrador desde el panel de administración")
    today = datetime.date.today()
    try:
        challenge = crud.create(db, current_user, body.kind, body.options, today)
    except ChallengeError as e:
        raise HTTPException(status_code=409 if "Ya existe" in str(e) else 400, detail=str(e))
    return crud.view(db, challenge, current_user.id, today)


@router.put("/{challenge_id}/participation")
def set_participation(
    challenge_id: int,
    joined: bool,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Stop taking part in a group challenge, or take part again. It is about the caller only."""
    challenge = _challenge(db, challenge_id, current_user)
    today = datetime.date.today()
    if not crud.can_opt_out(challenge, today):
        raise HTTPException(status_code=409, detail="En este reto no se puede cambiar la participación")
    crud.opt(db, challenge, current_user.id, joined)
    return crud.view(db, challenge, current_user.id, today)


@router.delete("/{challenge_id}")
def delete_challenge(
    challenge_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Delete a personal challenge of your own. The group's are deleted by an admin from the admin panel."""
    challenge = _challenge(db, challenge_id, current_user)
    if challenge.scope == GROUP or challenge.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="No puedes borrar este reto")
    crud.delete(db, challenge)
    return {"message": "Reto borrado"}
