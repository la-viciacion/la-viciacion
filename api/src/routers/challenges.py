import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import challenge_proposals as proposals
from ..crud import challenges as crud
from ..database import models
from ..utils import actions
from ..utils.challenges import DUEL, GROUP, TEMPLATES, ChallengeConflict, ChallengeError, available_tags

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


class NewProposal(BaseModel):
    kind: str
    options: dict = Field(default_factory=dict)


def _challenge(db: Session, challenge_id: int, viewer: models.User) -> models.Challenge:
    """A challenge the viewer may see (every public one and their own)."""
    found = db.get(models.Challenge, challenge_id)
    if found is None or (found.visibility != "public" and found.owner_user_id != viewer.id and not viewer.is_admin):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return found


@router.get("/genres")
def get_genres(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The genres "try a genre" can be about: those that exist in the database and have games, with how many and
    whether the caller already has one in their library."""
    return crud.genres(db, current_user.id)


@router.get("/debt")
def get_debt(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The caller's debt as a "reduce the debt" challenge launched today would start from it: seconds left to play,
    games that owe time and games open. Derived, so the form can say how many hours a percentage is."""
    return crud.debt_preview(db, current_user.id, datetime.date.today())


@router.get("/tags")
def get_tags(db: Session = Depends(get_db)):
    """The tags a themed challenge can be about (those of the games in the database, with how many have each): what a
    player needs to propose one."""
    return [{"tag": name, "games": count} for _, (name, count) in sorted(available_tags(db).items())]


@router.get("/proposals")
def get_my_proposals(
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """The group challenges the caller has proposed, with what the admins answered."""
    return proposals.mine(db, current_user.id)


@router.post("/proposals", status_code=201)
def propose_challenge(
    body: NewProposal,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Propose a challenge for the whole group (a game of the month or a themed one). It is not launched: an admin
    approves or rejects it from the panel. A player may have a few waiting at once."""
    try:
        proposal = proposals.propose(db, current_user, body.kind, body.options, datetime.date.today())
    except ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    background_tasks.add_task(actions.after_proposal_made, proposal.id)
    return proposals.view(db, proposal)


@router.delete("/proposals/{proposal_id}")
def withdraw_proposal(
    proposal_id: int,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Take back a proposal of your own that nobody has decided yet."""
    proposal = db.get(models.ChallengeProposal, proposal_id)
    if proposal is None or proposal.proposer_id != current_user.id:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    try:
        proposals.withdraw(db, proposal)
    except ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"message": "Propuesta retirada"}


@router.get("")
def get_challenges(
    status: Literal["active"] | None = None,
    finished_per_block: int | None = Query(None, ge=0, le=500, description="Only the latest finished ones of each block of the page; default: all of them"),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Every challenge the caller can see with its progress (derived; only the definition is stored). `status=active`
    keeps those running today, so a page that only needs those (the Home) does not work out the progress of every
    challenge there ever was. The same goes for `finished_per_block`: the page shows the latest few finished challenges of each
    of its blocks (the group's, yours, your duels, the others'), so it asks for those and only works out their progress."""
    today = datetime.date.today()
    visible = crud.visible(db, current_user.id, today if status == "active" else None, finished_per_block, today)
    return [crud.view(db, challenge, current_user.id, today) for challenge in visible]


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
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Launch a **personal** challenge from a template, for the caller (or a **duel** against another player: it starts
    at once and the other player may decline it for a couple of days). The group's challenges are the app's, not a
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
    except ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if challenge.scope == DUEL:
        background_tasks.add_task(actions.after_duel_launch, challenge.id)
    return crud.view(db, challenge, current_user.id, today)


@router.put("/{challenge_id}/participation")
def set_participation(
    challenge_id: int,
    joined: bool,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Stop taking part in a group challenge, or take part again. It is about the caller only. In a duel it is how the
    challenged player declines it (a decline is final), only during the first hours after it was launched."""
    challenge = _challenge(db, challenge_id, current_user)
    today = datetime.date.today()
    if not crud.can_opt_out(challenge, today, current_user.id):
        raise HTTPException(status_code=409, detail="En este reto no se puede cambiar la participación")
    if challenge.scope == DUEL and joined:
        raise HTTPException(status_code=409, detail="Un duelo solo se puede rechazar: no hace falta aceptarlo, empieza al lanzarlo")
    already_declined = crud.declined(db, challenge)
    crud.opt(db, challenge, current_user.id, joined)
    if challenge.scope == DUEL and not already_declined:  # a decline is final: it is told once
        background_tasks.add_task(actions.after_duel_decline, challenge.id)
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
