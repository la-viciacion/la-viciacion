"""The polls an admin launches into the Telegram group, and the answers the bot reports."""
import asyncio
import datetime
from typing import Optional, Union

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...crud import group_polls
from ...database import models
from ...utils import polls
from .common import get_or_404, router


@router.get("/polls")
def list_polls(db: Session = Depends(get_db)):
    """Every poll, the latest first, with its tally and who voted what."""
    rows = db.query(models.GroupPoll).order_by(models.GroupPoll.created_at.desc(), models.GroupPoll.id.desc())
    return [group_polls.view(db, poll) for poll in rows]


class NewPoll(BaseModel):
    question: str
    options: Union[list[str], str]  # the panel's form posts one option per line
    multiple: bool = False  # several answers allowed
    closes_at: Optional[datetime.datetime] = None  # the deadline; without one it is closed by hand


@router.post("/polls", status_code=201)
def launch_poll(body: NewPoll, admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Send a non-anonymous poll to the Telegram group. Not tied to the notifications switch: an admin asked for it."""
    options = body.options.splitlines() if isinstance(body.options, str) else body.options
    try:
        question, options = group_polls.clean(body.question, options, body.closes_at, datetime.datetime.now())
    except group_polls.PollError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        # a plain def runs in a worker thread: the loop it starts there is not the one that serves the other requests
        poll = asyncio.run(polls.launch(db, admin, question, options, body.multiple, body.closes_at))
    except polls.TelegramFailure as e:
        raise HTTPException(status_code=502, detail=str(e))
    return group_polls.view(db, poll)


class Closing(BaseModel):
    announce: bool = True  # tell the group the winner


@router.post("/polls/{poll_id}/close")
def close_poll(poll_id: int, body: Closing = Closing(), admin: models.User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    """Close a poll: it is closed here whatever Telegram does, and Telegram is told to stop it. Asking again for one that
    is already closed tries once more to stop it in Telegram if that had failed, and announces nothing."""
    poll = get_or_404(db, models.GroupPoll, poll_id, "Encuesta")
    asyncio.run(polls.close(db, poll, admin.id, body.announce, datetime.datetime.now()))
    return group_polls.view(db, poll)


@router.delete("/polls/{poll_id}")
def delete_poll(poll_id: int, db: Session = Depends(get_db)):
    """Delete a closed poll with its votes (the message stays in the group)."""
    poll = get_or_404(db, models.GroupPoll, poll_id, "Encuesta")
    if poll.closed_at is None:
        raise HTTPException(status_code=409, detail="Cierra la encuesta antes de borrarla")
    db.delete(poll)
    db.commit()
    return {"message": "Encuesta eliminada"}


class Answer(BaseModel):
    poll_id: str  # Telegram's id of the poll
    user_id: int  # Telegram's id of who answered
    option_ids: list[int]  # what they chose now; none = they took their vote back


@router.put("/polls/answers")
def record_answer(body: Answer, db: Session = Depends(get_db)):
    """What the bot reports when someone answers a poll of the group. It is not kept in the audit log (one row per vote would
    bury the changes of the admins). An answer to a poll that is not ours or is closed here counts for nothing."""
    return {"recorded": group_polls.record_answer(db, body.poll_id, body.user_id, body.option_ids, datetime.datetime.now())}
