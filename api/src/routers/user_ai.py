"""A player's own AI key (see utils/user_ai.py): save it, choose its model, take it away, try it.

Only the player may use these routes, an admin included: the key is theirs and what it spends is their money. Nothing here
returns the key, not even to its owner: they see whether they have one, its last four characters and the model."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..clients import failure as provider_failure
from ..clients import open_ai
from ..clients.ai_error import AIError, ProviderError, QuotaError
from ..database import models
from ..guide import agent as guide_agent
from ..utils import ai_budget, ai_models, ai_source, ai_spend, messages, user_ai
from ..utils.logger import LogManager
from ..utils.rate_limit import Scope, UsageLimiter
from .chat import PROVIDER_MESSAGES

logger = LogManager().get_logger()

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

DEFAULT_MODEL = "gpt-4.1-mini"  # cheap, and it can search the web (the guide needs it)
# Saving a key and trying it call OpenAI: a few a day are plenty, and a stolen session cannot be used to test keys in bulk
limiter = UsageLimiter()
CHANGES_PER_HOUR = 10
# Listing the models of a key already saved tests nothing (the screen asks every time it opens), so it has its own, wider limit
# and never uses up the saves and tests above
LISTINGS_PER_HOUR = 60


class AiKeyBody(BaseModel):
    # called api_key on purpose: error reports mask any field named like that
    api_key: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=64)


def _mine(active_user: models.User, username: str) -> models.User:
    auth.ensure_self(active_user, username)
    return active_user


def _limited(user: models.User, listing: bool = False) -> None:
    scope = Scope(f"ai-models:{user.id}", "user", ((3600, LISTINGS_PER_HOUR),)) if listing else Scope(f"ai-key:{user.id}", "user", ((3600, CHANGES_PER_HOUR),))
    refused = limiter.acquire([scope])
    if refused:
        raise HTTPException(status_code=429, detail=messages.USER_AI_TOO_MANY, headers={"Retry-After": str(refused.wait)})


def _provider_error(e: AIError) -> HTTPException:
    """What an error from OpenAI says to the player about THEIR key (never the key itself)."""
    if isinstance(e, QuotaError):
        return HTTPException(status_code=429, detail=messages.USER_KEY_QUOTA.format(when=""))
    kind = getattr(e, "kind", None)
    if kind == provider_failure.DENIED:
        return HTTPException(status_code=400, detail=messages.USER_AI_KEY_REJECTED)
    if isinstance(e, ProviderError):
        return HTTPException(status_code=504 if kind == provider_failure.TIMEOUT else 502, detail=PROVIDER_MESSAGES[kind])
    logger.warning(f"A player's AI key could not be checked: {e}")
    return HTTPException(status_code=502, detail=messages.CHAT_FAILED)


@router.get("/{username}/ai")
def get_ai(username: str, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """What the player has: whether there is a key of their own (its last characters and model), who pays for the chat and the
    guide now, and the default model offered."""
    user = _mine(active_user, username)
    return {
        "key": user_ai.status(db, user.id),
        "chat": ai_source.availability(db, user.id, "chat") | {"mode": ai_source.mode("chat")},
        "guide": ai_source.availability(db, user.id, "guide") | {"mode": ai_source.mode("guide")},
        "default_model": DEFAULT_MODEL,
        "budget": ai_budget.usage(db, user.id),
    }


@router.get("/{username}/ai/usage")
def get_ai_usage(
    username: str,
    month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    active_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(get_db),
):
    """What the player has used of the AI, from the record of their own calls (an estimate: the tokens measured and priced when
    each call was made): totals, what they paid with their own key against what the group's covered, by month (and by day for
    one month), by function and by model. Only theirs, an admin included; and the budget of the group's key this month."""
    user = _mine(active_user, username)
    data = ai_spend.summary(db, month, user_id=user.id)
    for admin_only in ("group_paid_by_user", "by_tools", "price_stamp"):
        data.pop(admin_only, None)
    return {**data, "budget": ai_budget.usage(db, user.id)}


@router.put("/{username}/ai")
def put_ai(username: str, body: AiKeyBody, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Saves a key (checked with OpenAI first, which spends nothing) and its model, or only changes the model of the key already
    saved. The model is the player's decision: any name is accepted."""
    user = _mine(active_user, username)
    model = user_ai.clean_model(body.model) if body.model is not None else None
    if body.model is not None and model is None:
        raise HTTPException(status_code=400, detail=messages.USER_AI_MODEL_INVALID)
    if body.api_key is None:
        if model is None:
            raise HTTPException(status_code=400, detail=messages.USER_AI_KEY_INVALID)
        if not user_ai.set_model(db, user.id, model):
            raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
        return user_ai.status(db, user.id)
    key = user_ai.clean_key(body.api_key)
    if key is None:
        raise HTTPException(status_code=400, detail=messages.USER_AI_KEY_INVALID)
    _limited(user)
    try:
        open_ai.list_models(key)
    except AIError as e:
        raise _provider_error(e) from None
    user_ai.save(db, user.id, key, model or user_ai.model_of(db, user.id) or DEFAULT_MODEL)  # replacing a key keeps the model chosen
    return user_ai.status(db, user.id)


@router.delete("/{username}/ai")
def delete_ai(username: str, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Takes the player's key away: from then on the group's key is used where the group allows it."""
    user = _mine(active_user, username)
    user_ai.clear(db, user.id)
    return user_ai.status(db, user.id)


@router.get("/{username}/ai/models")
def get_ai_models(username: str, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """The models the player's key can use that answer a chat, each with its tier and its price per million tokens (an
    estimate: the model is their decision, whatever it costs)."""
    user = _mine(active_user, username)
    found = user_ai.credentials(db, user.id)
    if found is None:
        raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
    _limited(user, listing=True)
    try:
        ids = open_ai.list_models(found[0])
    except AIError as e:
        raise _provider_error(e) from None
    return {"models": ai_models.describe(ids), "current": found[1]}


@router.post("/{username}/ai/test")
def test_ai(username: str, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Asks one question that needs the web search with the player's key and model: it tells whether the model works for the
    guide. It spends a little of THEIR account (the call and one search)."""
    user = _mine(active_user, username)
    source = ai_source.own_source(db, user.id)
    if source is None:
        raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
    _limited(user)
    try:
        reply = guide_agent.probe(source=source)
    except AIError as e:
        logger.warning(f"A player's own AI key failed its test: {type(e).__name__}")
        raise _provider_error(e) from None
    return {"reply": reply, "model": source.model}
