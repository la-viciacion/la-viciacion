"""A player's own AI keys, one for each provider (see utils/user_ai.py): unlock them, save one, choose its model, take it away, try it,
and say which provider to use first.

Only the player may use these routes, an admin included: the keys are theirs and what they spend is their money. Nothing here returns a
key, not even to its owner: they see whether they have one, its last four characters (while unlocked) and the model. The keys are
sealed with a data key that only their password opens, and a session carries it in its token: one that does not is **locked** (423) and
`POST /users/{username}/ai/unlock` is how the player opens it with their password."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..clients import failure as provider_failure
from ..clients import model_list
from ..clients.ai_error import AIError, ProviderError, QuotaError
from ..database import models
from ..guide import agent as guide_agent
from ..utils import ai_budget, ai_ledger, ai_models, ai_source, ai_spend, ai_wallet, audit, messages, settings, user_ai
from ..utils.logger import LogManager
from ..utils.rate_limit import AttemptLimiter, Scope, UsageLimiter
from .chat import PROVIDER_MESSAGES

logger = LogManager().get_logger()

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={404: {"description": "Not found"}},
    dependencies=[Depends(auth.get_current_active_user)],
)

PROVIDER = "^(" + "|".join(settings.AI_PROVIDERS) + ")$"
ProviderName = Annotated[str, Path(pattern=PROVIDER)]
PROVIDER_NAMES = {"openai": "OpenAI", "google": "Google", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
WHERE_TO_MAKE_IT = {
    "openai": "platform.openai.com → API keys", "google": "aistudio.google.com → API keys",
    "anthropic": "platform.claude.com → API keys", "openrouter": "openrouter.ai/settings/keys",
}
# Saving a key and trying it call the provider: a few a day are plenty, and a stolen session cannot be used to test keys in bulk
limiter = UsageLimiter()
CHANGES_PER_HOUR = 10
# Listing the models of a key already saved tests nothing (the screen asks every time it opens), so it has its own, wider limit
# and never uses up the saves and tests above
LISTINGS_PER_HOUR = 60
# The password typed to unlock the keys is guessed like the one of the login: five wrong ones close the door for a quarter of an hour
UNLOCK_BY_ACCOUNT = AttemptLimiter(max_failures=5, window_seconds=15 * 60)


class AiKeyBody(BaseModel):
    # called api_key on purpose: error reports mask any field named like that
    api_key: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=80)


class UnlockBody(BaseModel):
    password: str = Field(min_length=1, max_length=200)


class PreferredBody(BaseModel):
    provider: str | None = Field(default=None, pattern=PROVIDER)


def _mine(active_user: models.User, username: str) -> models.User:
    auth.ensure_self(active_user, username)
    return active_user


def _unlocked(dek: bytes | None) -> bytes:
    """The data key of the session, or 423: the keys are locked until the player types their password."""
    if dek is None:
        raise HTTPException(status_code=423, detail=messages.USER_AI_LOCKED)
    return dek


def _credentials(db: Session, user: models.User, dek: bytes | None, provider: str) -> tuple[str, str]:
    """(key, model) of the player's own for `provider`: 409 if they have none, 423 if the session cannot open it."""
    if provider not in user_ai.providers_with_key(db, user.id):
        raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
    found = user_ai.credentials(db, user.id, _unlocked(dek), provider)
    if found is None:
        raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)  # it is saved but does not open with this data key
    return found


def _limited(user: models.User, listing: bool = False) -> None:
    scope = Scope(f"ai-models:{user.id}", "user", ((3600, LISTINGS_PER_HOUR),)) if listing else Scope(f"ai-key:{user.id}", "user", ((3600, CHANGES_PER_HOUR),))
    refused = limiter.acquire([scope])
    if refused:
        raise HTTPException(status_code=429, detail=messages.USER_AI_TOO_MANY, headers={"Retry-After": str(refused.wait)})


def _provider_error(e: AIError, provider: str) -> HTTPException:
    """What an error from a provider says to the player about THEIR key (never the key itself)."""
    if isinstance(e, QuotaError):
        return HTTPException(status_code=429, detail=messages.USER_KEY_QUOTA.format(when=""))
    kind = getattr(e, "kind", None)
    if kind == provider_failure.DENIED:
        return HTTPException(status_code=400, detail=messages.USER_AI_KEY_REJECTED.format(provider=PROVIDER_NAMES[provider], where=WHERE_TO_MAKE_IT[provider]))
    if isinstance(e, ProviderError):
        return HTTPException(status_code=504 if kind == provider_failure.TIMEOUT else 502, detail=PROVIDER_MESSAGES[kind])
    logger.warning(f"A player's {provider} key could not be checked: {type(e).__name__}")
    return HTTPException(status_code=502, detail=messages.CHAT_FAILED)


def _state(db: Session, user: models.User, dek: bytes | None) -> dict:
    return {
        **user_ai.status(db, user.id, dek),
        "chat": ai_source.availability(db, user.id, "chat", dek) | {"mode": ai_source.mode("chat")},
        "guide": ai_source.availability(db, user.id, "guide", dek) | {"mode": ai_source.mode("guide")},
        "budget": ai_budget.usage(db, user.id),
        "wallet": ai_wallet.player(db, user.id),
    }


@router.get("/{username}/ai")
def get_ai(username: str, active_user: models.User = Depends(auth.get_current_active_user), dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db)):
    """What the player has: their keys (whether each exists, its last characters while unlocked, its model), whether the session is
    **locked**, the provider they prefer, who pays for the chat and the guide now, the model each provider starts with, and the budgets."""
    user = _mine(active_user, username)
    return _state(db, user, dek)


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
    return {**data, "budget": ai_budget.usage(db, user.id), "wallet": ai_wallet.player(db, user.id)}


@router.post("/{username}/ai/unlock")
def unlock_ai(
    request: Request, username: str, body: UnlockBody, active_user: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)
):
    """Opens the keys of this session with the player's password (the data key is made the first time). It answers a new token, which
    carries it: the front keeps it in place of the one it had. Wrong passwords are counted like those of the login."""
    user = _mine(active_user, username)
    wait = UNLOCK_BY_ACCOUNT.retry_after(str(user.id))
    if wait:
        raise HTTPException(status_code=429, detail=messages.USER_AI_TOO_MANY, headers={"Retry-After": str(wait)})
    if not auth.verify_password(body.password, user.password):
        UNLOCK_BY_ACCOUNT.fail(str(user.id))
        audit.record_event(request, "ai_unlock_failed", 400, user=user)
        raise HTTPException(status_code=400, detail=messages.PASSWORD_WRONG)
    UNLOCK_BY_ACCOUNT.reset(str(user.id))
    dek = user_ai.unlock(db, user.id, body.password)
    return {**auth.issue_token(user, dek), **_state(db, user, dek)}


# defined before the routes of a provider: a fixed word, so it is never taken for one
@router.put("/{username}/ai/preferred")
def put_preferred(
    username: str, body: PreferredBody, active_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db),
):
    """Says which provider's key to use first (null: the app picks). It must be one the player has a key for."""
    user = _mine(active_user, username)
    if body.provider is not None and body.provider not in user_ai.providers_with_key(db, user.id):
        raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
    user_ai.set_preferred(db, user.id, body.provider)
    return _state(db, user, dek)


@router.put("/{username}/ai/{provider}")
def put_ai(
    username: str, provider: ProviderName, body: AiKeyBody, active_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db),
):
    """Saves a key of `provider` (checked with the provider first, which spends nothing) and its model, or only changes the model of the
    key already saved. The model is the player's decision: any name is accepted. Saving needs the keys unlocked; changing the model
    does not (it touches no secret)."""
    user = _mine(active_user, username)
    model = user_ai.clean_model(body.model) if body.model is not None else None
    if body.model is not None and model is None:
        raise HTTPException(status_code=400, detail=messages.USER_AI_MODEL_INVALID)
    if body.api_key is None:
        if model is None:
            raise HTTPException(status_code=400, detail=messages.USER_AI_KEY_INVALID.format(provider=PROVIDER_NAMES[provider]))
        if not user_ai.set_model(db, user.id, provider, model):
            raise HTTPException(status_code=409, detail=messages.USER_AI_NO_KEY)
        return _state(db, user, dek)
    key = user_ai.clean_key(provider, body.api_key)
    if key is None:
        raise HTTPException(status_code=400, detail=messages.USER_AI_KEY_INVALID.format(provider=PROVIDER_NAMES[provider]))
    opened = _unlocked(dek)
    _limited(user)
    try:
        model_list.list_models(provider, key)
    except AIError as e:
        raise _provider_error(e, provider) from None
    user_ai.save(db, user.id, opened, provider, key, model)  # replacing a key keeps the model chosen
    return _state(db, user, dek)


@router.delete("/{username}/ai/{provider}")
def delete_ai(
    username: str, provider: ProviderName, active_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db),
):
    """Takes the player's key of `provider` away: from then on the group's key is used where the group allows it. It needs no unlock:
    nothing is opened to delete it."""
    user = _mine(active_user, username)
    user_ai.clear(db, user.id, provider)
    return _state(db, user, dek)


@router.get("/{username}/ai/{provider}/models")
def get_ai_models(
    username: str, provider: ProviderName, active_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db),
):
    """The models the player's key of `provider` can use that answer a chat, each with its tier and its price per million tokens (an
    estimate: the model is their decision, whatever it costs)."""
    user = _mine(active_user, username)
    found = _credentials(db, user, dek, provider)
    _limited(user, listing=True)
    try:
        ids = model_list.list_models(provider, found[0])
    except AIError as e:
        raise _provider_error(e, provider) from None
    return {"models": ai_models.describe(ids, provider), "current": found[1]}


@router.post("/{username}/ai/{provider}/test")
def test_ai(
    username: str, provider: ProviderName, active_user: models.User = Depends(auth.get_current_active_user),
    dek: bytes | None = Depends(auth.get_unlock), db: Session = Depends(get_db),
):
    """Asks one question that needs the web search with the player's key and model of `provider`: it tells whether the model works for
    the guide. It spends a little of THEIR account (the call and one search)."""
    user = _mine(active_user, username)
    found = _credentials(db, user, dek, provider)
    _limited(user)
    source = ai_source.Source(ai_ledger.USER, provider, found[0], found[1])
    try:
        reply = guide_agent.probe(source=source, user_id=user.id)
    except AIError as e:
        logger.warning(f"A player's own {provider} key failed its test: {type(e).__name__}")
        raise _provider_error(e, provider) from None
    return {"reply": reply, "model": source.model, "provider": provider}
