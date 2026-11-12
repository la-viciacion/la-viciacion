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
from ..utils import ai_ledger, ai_source, messages
from ..utils.logger import LogManager
from .chat import PROVIDER_MESSAGES, ChatTurn, own_key_detail, refusal

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
def get_status(current_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """What this player can do with the guide now: `available` (it is on and somebody could pay for it), `needs_key` (the
    group does not cover it: they have to save their own key) and `paid_by` (`user` or `group`, who would pay)."""
    return ai_source.availability(db, current_user.id, "guide")  # `blocked`: the budget of the group's key is spent


@router.post("/{game_id}", response_model=GuideResponse)
def ask(
    game_id: str,
    body: GuideRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """Answers a question about one game, searching the web. The history comes from the client; nothing is stored."""
    state = ai_source.availability(db, current_user.id, "guide")
    if not state["available"]:
        raise HTTPException(status_code=503, detail=messages.GUIDE_UNAVAILABLE)
    if state["blocked"]:
        ai_ledger.record(
            db, user_id=current_user.id, feature="guide", key_source=ai_ledger.GROUP, status=ai_ledger.BUDGET,
            question=body.message, turns=len(body.history), game_id=game_id,
        )
        raise HTTPException(status_code=429, detail=ai_source.blocked_message(state["blocked"], "guide"))
    if state["needs_key"]:
        raise HTTPException(status_code=403, detail=messages.USER_KEY_REQUIRED)
    source = ai_source.resolve(db, current_user.id, "guide")
    data = game_overview.overview(db, game_id, current_user.id)
    if data is None:
        raise HTTPException(status_code=404, detail="Game not exists")
    refused = limits.limiter.acquire(limits.scopes_of(current_user.id, source.own))
    if refused:
        ai_ledger.record(
            db, user_id=current_user.id, feature="guide", key_source=source.key_source, status=ai_ledger.LIMITED,
            question=body.message, turns=len(body.history), game_id=game_id,
        )
        raise refusal(refused)
    deps = agent.GuideDeps(
        game=agent.game_context(data), level=body.level, user_name=current_user.name or current_user.username,
        db=db, user_id=current_user.id, game_id=game_id, source=source,
    )
    try:
        answer = agent.ask(deps, body.message.strip(), [(t.role, t.content) for t in body.history])
    except QuotaError as e:
        retry = e.quota.retry_after
        raise HTTPException(
            status_code=429,
            detail=own_key_detail(source, e) or messages.CHAT_QUOTA.format(when=f" (reintenta en {wait_text(retry)})" if retry else ""),
            headers={"Retry-After": str(retry)} if retry else None,
        )
    except ProviderError as e:
        # a provider that is slow, or a player's own key that was revoked, is not a bug of ours: a warning, not an event in Sentry
        ours = e.kind not in (provider_failure.TIMEOUT, provider_failure.OVERLOADED) and not (source.own and e.kind == provider_failure.DENIED)
        (logger.error if ours else logger.warning)("Guide failed: " + str(e), exc_info=ours)
        raise HTTPException(status_code=504 if e.kind == provider_failure.TIMEOUT else 502, detail=own_key_detail(source, e) or PROVIDER_MESSAGES[e.kind])
    except AIError as e:
        logger.error("Guide failed: " + str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=messages.CHAT_FAILED)
    return GuideResponse(answer=answer)
