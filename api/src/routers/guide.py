from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..clients import failure as provider_failure
from ..clients.ai_error import AIError, ProviderError, QuotaError, wait_text
from ..crud import game_overview
from ..database import models
from ..guide import agent, limits
from ..utils import ai_ledger, messages
from ..utils.logger import LogManager
from .chat import PROVIDER_MESSAGES, ChatTurn, refusal

logger = LogManager().get_logger()

router = APIRouter(
    prefix="/guide",
    tags=["Guide"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)


class GuideRequest(BaseModel):
    message: str = Field(min_length=1, max_length=agent.MAX_QUESTION)
    level: Literal["nudge", "hint", "solution"] = "nudge"
    history: list[ChatTurn] = Field(default_factory=list, max_length=agent.MAX_HISTORY)


class GuideResponse(BaseModel):
    answer: str


@router.get("/status")
def get_status():
    """Whether the guide can answer now, so the game page only offers it when it works"""
    return {"available": agent.is_ready()}


@router.post("/{game_id}", response_model=GuideResponse)
def ask(
    game_id: str,
    body: GuideRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Answers a question about one game, searching the web. The history comes from the client; nothing is stored."""
    if not agent.is_ready():
        raise HTTPException(status_code=503, detail=messages.GUIDE_UNAVAILABLE)
    data = game_overview.overview(db, game_id, current_user.id)
    if data is None:
        raise HTTPException(status_code=404, detail="Game not exists")
    refused = limits.limiter.acquire(limits.scopes_of(current_user.id))
    if refused:
        ai_ledger.record(
            db, user_id=current_user.id, feature="guide", key_source=ai_ledger.GROUP, status=ai_ledger.LIMITED,
            question=body.message, turns=len(body.history), game_id=game_id,
        )
        raise refusal(refused)
    deps = agent.GuideDeps(
        game=agent.game_context(data), level=body.level, user_name=current_user.name or current_user.username,
        db=db, user_id=current_user.id, game_id=game_id,
    )
    try:
        answer = agent.ask(deps, body.message.strip(), [(t.role, t.content) for t in body.history])
    except QuotaError as e:
        retry = e.quota.retry_after
        raise HTTPException(
            status_code=429,
            detail=messages.CHAT_QUOTA.format(when=f" (reintenta en {wait_text(retry)})" if retry else ""),
            headers={"Retry-After": str(retry)} if retry else None,
        )
    except ProviderError as e:
        transient = e.kind in (provider_failure.TIMEOUT, provider_failure.OVERLOADED)
        (logger.warning if transient else logger.error)("Guide failed: " + str(e), exc_info=not transient)
        raise HTTPException(status_code=504 if e.kind == provider_failure.TIMEOUT else 502, detail=PROVIDER_MESSAGES[e.kind])
    except AIError as e:
        logger.error("Guide failed: " + str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=messages.CHAT_FAILED)
    return GuideResponse(answer=answer)
