from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..chat import agent
from ..chat import model as chat_model
from ..clients.ai_error import AIError
from ..database import models
from ..utils import messages
from ..utils.logger import LogManager
from ..utils.rate_limit import AttemptLimiter

log_manager = LogManager()
logger = log_manager.get_logger()

router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

# Each question costs a call to a paid model: this keeps one account (or a leaked token) from emptying the quota
QUESTIONS_PER_HOUR = 30
limiter = AttemptLimiter(max_failures=QUESTIONS_PER_HOUR, window_seconds=3600)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
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
    wait = limiter.retry_after(str(current_user.id))
    if wait:
        raise HTTPException(status_code=429, detail=messages.CHAT_RATE_LIMITED.format(minutes=wait // 60 + 1), headers={"Retry-After": str(wait)})
    limiter.fail(str(current_user.id))  # not a failure: the limiter just counts the attempts
    try:
        answer = agent.ask(db, current_user, body.message.strip(), [(t.role, t.content) for t in body.history])
    except AIError as e:
        logger.error("Chat failed: " + str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=messages.CHAT_FAILED)
    return ChatResponse(answer=answer.text, in_scope=answer.in_scope)
