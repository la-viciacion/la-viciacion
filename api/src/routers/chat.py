from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..chat import agent, limits
from ..clients.ai_error import wait_text
from ..database import models
from ..utils import ai_fallback, ai_ledger, ai_source, in_flight, messages, user_settings
from ..utils.rate_limit import Refused

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

WHEN = {60: "el último minuto", 3600: "la última hora", 86400: "las últimas 24 horas"}


def refusal(refused: Refused) -> HTTPException:
    template = messages.CHAT_GROUP_LIMITED if refused.scope == "group" else messages.CHAT_USER_LIMITED
    return HTTPException(
        status_code=429,
        detail=template.format(when=WHEN[refused.window], wait=wait_text(refused.wait)),
        headers={"Retry-After": str(refused.wait)},
    )


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=limits.MAX_QUESTION)
    history: list[ChatTurn] = Field(default_factory=list, max_length=agent.MAX_HISTORY)


class ChatResponse(BaseModel):
    answer: str
    in_scope: bool


@router.get("/status")
def get_status(
    current_user: models.User = Depends(auth.get_current_active_user), dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db)
):
    """Whether the chat is there for this player (it is on and somebody can pay for it: their own key, or the group's), so the
    front only shows it when it works. One whose budget is spent still sees it: asking tells them why it does not answer.
    `bubble` is the player's own choice to see the button (the profile offers the switch only where `available`)."""
    decision = ai_source.decide(db, current_user.id, "chat", dek)
    return {
        "available": decision.source is not None or decision.blocked is not None or decision.locked,
        "bubble": user_settings.show_chat(db, current_user.id),
    }


@router.post("", response_model=ChatResponse)
def ask(
    body: ChatRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock),
    db: Session = Depends(get_db),
):
    """Answers a question about video games and the group's data. Read-only: the history comes from the client and
    nothing of the conversation is stored."""
    decision = ai_source.decide(db, current_user.id, "chat", dek)
    if decision.blocked and decision.source is None:  # with the player's own as the source it only says why the group's was not used
        ai_ledger.record_blocked(db, user_id=current_user.id, feature="chat", question=body.message, turns=len(body.history))
        raise HTTPException(status_code=429, detail=ai_source.blocked_message(decision.blocked, "chat", decision.locked))
    source = decision.source
    if source is None and decision.locked:  # they have keys, this session cannot open them: the front asks for the password
        raise HTTPException(status_code=423, detail=messages.USER_AI_LOCKED)
    if source is None:
        raise HTTPException(status_code=503, detail=messages.CHAT_UNAVAILABLE)
    with in_flight.one_at_a_time(current_user.id, source.own):
        refused = limits.limiter.acquire(limits.scopes_of(current_user.id, source.own))
        if refused:
            ai_ledger.record(
                db, user_id=current_user.id, feature="chat", key_source=source.key_source, status=ai_ledger.LIMITED,
                question=body.message, turns=len(body.history),
            )
            raise refusal(refused)
        history = [(t.role, t.content) for t in body.history]
        try:
            # the group's key first and, if the provider says it cannot pay, the player's own ones (utils/ai_fallback.py)
            answer = ai_fallback.run(
                decision.sources, lambda chosen: agent.ask(db, current_user, body.message.strip(), history, source=chosen), "chat"
            )
        except ai_fallback.Failed as failed:
            raise ai_fallback.explain(failed.attempts, lambda: ai_source.way_out("chat", decision.fallback_locked))
        return ChatResponse(answer=answer.text, in_scope=answer.in_scope)
