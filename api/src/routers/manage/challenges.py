"""The group's challenges: launched and deleted only here."""
import datetime
from typing import Optional

from fastapi import BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...crud import challenge_proposals as proposals_crud
from ...crud import challenge_schedules as schedules_crud
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
            "participation": challenge.participation,
            "created_by": owner.username if owner else None,
            "owner": shown["owner"]["name"] if shown["owner"] else None,
            "players": len(shown["progress"]["players"]),
            "done_players": sum(1 for p in shown["progress"]["players"] if p["done"]),
            "total_done": shown["progress"].get("total_done"),
            "notified": challenge.total_notified_at is not None,
        })
    return rows


@router.get("/challenges/themes")
def list_challenge_themes(db: Session = Depends(get_db)):
    """The themes a themed challenge can be about (utils/themes.py): those that have games, with how many, the most first."""
    return challenges_utils.themes_listing(db)


class NewGroupChallenge(BaseModel):
    kind: str = "game_of_month"
    # the options of the templates, flat (the panel's form posts them as they are); each template reads its own
    game_id: Optional[str] = None
    month: Optional[str] = None
    starts_on: Optional[str] = None  # free dates instead of a month ("YYYY-MM-DD", both inclusive)
    ends_on: Optional[str] = None
    min_hours_each: Optional[float] = None
    min_hours_total: Optional[float] = None
    theme: Optional[str] = None
    tag: Optional[str] = None  # what a theme was before: an older client or a schedule still sends it
    mode: Optional[str] = None
    min_games_total: Optional[int] = None
    versus: Optional[bool] = None  # also rank who got furthest
    participation: Optional[str] = None  # "auto" (everybody, the default) or "opt_in" (only who joins)
    announce: bool = True  # tell the group (Telegram and push) that it was launched


@router.post("/challenges", status_code=201)
def launch_group_challenge(body: NewGroupChallenge, background_tasks: BackgroundTasks, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Launch a challenge for the whole group. They are the app's, so only here (the audit log records who) and
    never from the challenges page, where players launch their own."""
    template = challenges_utils.TEMPLATES.get(body.kind)
    if template is None or template.scope != challenges_utils.GROUP:
        raise HTTPException(status_code=400, detail="Ese tipo de reto de grupo no existe")
    options = body.model_dump(exclude={"kind", "announce", "participation"}, exclude_none=True)
    today = datetime.date.today()
    try:
        challenge = challenges_crud.create(db, admin, body.kind, options, today, body.participation or challenges_utils.AUTO)
    except challenges_utils.ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except challenges_utils.ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.announce:
        background_tasks.add_task(actions.after_challenge_launch, challenge.id)
    return challenges_crud.view(db, challenge, admin.id, today)


@router.delete("/challenges/{challenge_id}")
def delete_challenge(challenge_id: int, db: Session = Depends(get_db)):
    """Delete a challenge (its opt-outs go with it)."""
    challenges_crud.delete(db, get_or_404(db, models.Challenge, challenge_id, "Reto"))
    return {"message": "Reto eliminado"}


# ── the proposals of the players ────────────────────────────────


class Decision(BaseModel):
    announce: bool = True  # tell the group that the challenge was launched
    participation: str = challenges_utils.AUTO
    note: Optional[str] = None  # why it was rejected


def _proposal(db: Session, proposal_id: int) -> models.ChallengeProposal:
    return get_or_404(db, models.ChallengeProposal, proposal_id, "Propuesta")


@router.get("/challenge-proposals")
def list_proposals(status: Optional[str] = None, db: Session = Depends(get_db)):
    """The proposals of the players, the ones waiting first."""
    return proposals_crud.listing(db, status)


@router.post("/challenge-proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: int, background_tasks: BackgroundTasks, body: Decision = Decision(),
    admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db),
):
    """Launch what a player proposed, as a challenge of the group, and say so to the proposer (the panel and the
    challenges page show it). It fails if it cannot be launched any more (its month has passed): reject it then."""
    proposal = _proposal(db, proposal_id)
    try:
        challenge = proposals_crud.approve(db, proposal, admin, datetime.date.today(), body.participation)
    except challenges_utils.ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    except challenges_utils.ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.announce:
        background_tasks.add_task(actions.after_challenge_launch, challenge.id)
    background_tasks.add_task(actions.after_proposal_decided, proposal.id)
    return proposals_crud.view(db, proposal)


@router.post("/challenge-proposals/{proposal_id}/reject")
def reject_proposal(proposal_id: int, background_tasks: BackgroundTasks, body: Decision = Decision(), admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Turn a proposal down; the note is what the proposer reads."""
    try:
        proposal = proposals_crud.reject(db, _proposal(db, proposal_id), admin, body.note)
    except challenges_utils.ChallengeConflict as e:
        raise HTTPException(status_code=409, detail=str(e))
    background_tasks.add_task(actions.after_proposal_decided, proposal.id)
    return proposals_crud.view(db, proposal)


@router.delete("/challenge-proposals/{proposal_id}")
def delete_proposal(proposal_id: int, db: Session = Depends(get_db)):
    """Delete a proposal (the challenge it launched stays)."""
    proposal = _proposal(db, proposal_id)
    db.delete(proposal)
    db.commit()
    return {"message": "Propuesta eliminada"}


# ── the challenges that launch themselves every month ──────────


class NewSchedule(BaseModel):
    label: Optional[str] = None
    kind: str = "themed"
    # the options of the template, flat, without the month and the game (the schedule chooses them each month)
    min_hours_each: Optional[float] = None
    min_hours_total: Optional[float] = None
    theme: Optional[str] = None
    tag: Optional[str] = None  # what a theme was before: an older client or a schedule still sends it
    mode: Optional[str] = None
    min_games_total: Optional[int] = None
    versus: Optional[bool] = None
    games: Optional[list[str]] = None  # the rotation of a game of the month
    participation: Optional[str] = None
    announce: bool = False
    start_now: bool = False  # the running month counts; otherwise it starts next month


class ScheduleChanges(BaseModel):
    label: Optional[str] = None
    active: Optional[bool] = None
    announce: Optional[bool] = None
    participation: Optional[str] = None
    games: Optional[list[str]] = None


def _schedule(db: Session, schedule_id: int) -> models.ChallengeSchedule:
    return get_or_404(db, models.ChallengeSchedule, schedule_id, "Reto recurrente")


@router.get("/challenge-schedules")
def list_schedules(db: Session = Depends(get_db)):
    """The schedules, with the game of the running month and of the next one."""
    return schedules_crud.listing(db, datetime.date.today())


@router.post("/challenge-schedules", status_code=201)
def create_schedule(body: NewSchedule, background_tasks: BackgroundTasks, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Define a challenge that launches itself every month. With `start_now` the one of the running month is launched
    at once."""
    today = datetime.date.today()
    try:
        schedule = schedules_crud.create(db, admin, body.model_dump(exclude_none=True), today)
    except challenges_utils.ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    launched = schedules_crud.launch_due(db, schedule, today)
    if launched is not None and schedule.announce:
        background_tasks.add_task(actions.after_challenge_launch, launched.id)
    return schedules_crud.view(db, schedule, today)


@router.patch("/challenge-schedules/{schedule_id}")
def update_schedule(schedule_id: int, body: ScheduleChanges, db: Session = Depends(get_db)):
    """Change the name, whether it is active or announces, who takes part and the rotation of games."""
    today = datetime.date.today()
    try:
        schedule = schedules_crud.update(db, _schedule(db, schedule_id), body.model_dump(exclude_none=True), today)
    except challenges_utils.ChallengeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schedules_crud.view(db, schedule, today)


@router.delete("/challenge-schedules/{schedule_id}")
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Delete a schedule (the challenges it launched stay)."""
    db.delete(_schedule(db, schedule_id))
    db.commit()
    return {"message": "Reto recurrente eliminado"}
