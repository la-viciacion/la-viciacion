from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..crud import game_overview
from ..database import models
from ..guide import agent, limits
from ..utils import ai_fallback, ai_ledger, ai_source, in_flight, messages
from .chat import ChatTurn, refusal

router = APIRouter(
    prefix="/guide",
    tags=["Guide"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


class GuideRequest(BaseModel):
    message: str = Field(min_length=1, max_length=agent.MAX_QUESTION)
    level: Literal["nudge", "hint", "solution"] = "nudge"
    mode: Literal["normal", "extras", "completionist", "free"] = "normal"
    history: list[ChatTurn] = Field(default_factory=list, max_length=agent.MAX_HISTORY)


class GuideResponse(BaseModel):
    answer: str


@router.get("/status")
def get_status(
    current_user: models.User = Depends(auth.get_current_active_user), dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db)
):
    """What this player can do with the guide now: `available` (it is on and somebody could pay for it), `needs_key` (the
    group does not cover it: they have to save their own key), `paid_by` (`user` or `group`, who would pay) and `locked` (they have
    keys of their own that this session cannot open until they type their password)."""
    return ai_source.availability(db, current_user.id, "guide", dek)  # `blocked`: why the group's key cannot answer this player


@router.post("/{game_id}", response_model=GuideResponse)
def ask(
    game_id: str,
    body: GuideRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock),
    db: Session = Depends(get_db),
):
    """Answers a question about one game, searching the web. The history comes from the client; nothing is stored."""
    decision = ai_source.decide(db, current_user.id, "guide", dek)  # once: it opens the key and sums the month's spending
    state = ai_source.state_of("guide", decision)
    if not state["available"]:
        raise HTTPException(status_code=503, detail=messages.GUIDE_UNAVAILABLE)
    data = game_overview.overview(db, game_id, current_user.id)
    if data is None:  # before anything is recorded: a row about a game that does not exist would break its foreign key
        raise HTTPException(status_code=404, detail="Game not exists")
    if state["blocked"] and decision.source is None:  # with the player's own as the source it only says why the group's was not used
        ai_ledger.record_blocked(db, user_id=current_user.id, feature="guide", question=body.message, turns=len(body.history), game_id=game_id)
        raise HTTPException(status_code=429, detail=ai_source.blocked_message(state["blocked"], "guide", decision.locked))
    if decision.locked and decision.source is None:  # they have keys, this session cannot open them: the front asks for the password
        raise HTTPException(status_code=423, detail=messages.USER_AI_LOCKED)
    if state["needs_key"]:
        raise HTTPException(status_code=403, detail=messages.USER_KEY_REQUIRED)
    source = decision.source
    with in_flight.one_at_a_time(current_user.id, source.own):
        refused = limits.limiter.acquire(limits.scopes_of(current_user.id, source.own))
        if refused:
            ai_ledger.record(
                db, user_id=current_user.id, feature="guide", key_source=source.key_source, status=ai_ledger.LIMITED,
                question=body.message, turns=len(body.history), game_id=game_id,
            )
            raise refusal(refused)
        history = [(t.role, t.content) for t in body.history]

        def call_with(chosen):
            deps = agent.GuideDeps(
                game=agent.game_context(data, body.mode), level=body.level, user_name=current_user.name or current_user.username,
                db=db, user_id=current_user.id, game_id=game_id, source=chosen,
            )
            return agent.ask(deps, body.message.strip(), history)

        try:
            # the group's key first and, if the provider says it cannot pay, the player's own ones (utils/ai_fallback.py)
            answer = ai_fallback.run(decision.sources, call_with, "guide")
        except ai_fallback.Failed as failed:
            raise ai_fallback.explain(failed.attempts, lambda: ai_source.way_out("guide", decision.fallback_locked))
        return GuideResponse(answer=answer)
