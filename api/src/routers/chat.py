from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..chat import agent, limits
from ..chat import model as chat_model
from ..clients import failure as provider_failure
from ..clients.ai_error import AIError, ProviderError, QuotaError, wait_text
from ..database import models
from ..utils import messages
from ..utils.logger import LogManager
from ..utils.rate_limit import Refused

log_manager = LogManager()
logger = log_manager.get_logger()

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

PROVIDER_MESSAGES = {
    provider_failure.TIMEOUT: messages.CHAT_TIMEOUT,
    provider_failure.OVERLOADED: messages.CHAT_OVERLOADED,
    provider_failure.SERVER: messages.CHAT_SERVER,
    provider_failure.DENIED: messages.CHAT_DENIED,
}
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
def get_status():
    """Whether the chat can answer now (the AI is on for it and configured), so the front only shows it when it works"""
    return {"available": chat_model.is_ready()}


@router.post("", response_model=ChatResponse)
def ask(
    body: ChatRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Answers a question about video games and the group's data. Read-only: the history comes from the client and
    nothing of the conversation is stored."""
    if not chat_model.is_ready():
        raise HTTPException(status_code=503, detail=messages.CHAT_UNAVAILABLE)
    refused = limits.limiter.acquire(limits.scopes_of(current_user.id))
    if refused:
        raise refusal(refused)
    try:
        answer = agent.ask(db, current_user, body.message.strip(), [(t.role, t.content) for t in body.history])
    except QuotaError as e:
        # already written to the audit log by the agent; not an error of ours, so not one in Sentry either
        retry = e.quota.retry_after
        raise HTTPException(
            status_code=429,
            detail=messages.CHAT_QUOTA.format(when=f" (reintenta en {wait_text(retry)})" if retry else ""),
            headers={"Retry-After": str(retry)} if retry else None,
        )
    except ProviderError as e:
        # a provider that is slow or overloaded is not a bug of ours: a warning, not an event in Sentry. The status is 504 for a
        # timeout and 502 for the rest, never 503: the front reads that as "the admin switched the chat off"
        transient = e.kind in (provider_failure.TIMEOUT, provider_failure.OVERLOADED)
        (logger.warning if transient else logger.error)("Chat failed: " + str(e), exc_info=not transient)
        raise HTTPException(status_code=504 if e.kind == provider_failure.TIMEOUT else 502, detail=PROVIDER_MESSAGES[e.kind])
    except AIError as e:
        logger.error("Chat failed: " + str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=messages.CHAT_FAILED)
    return ChatResponse(answer=answer.text, in_scope=answer.in_scope)
