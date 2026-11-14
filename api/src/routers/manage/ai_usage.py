"""What the AI has cost: OpenAI's billed spend, and the calls the app made (what it used, who paid, the kind of question)."""
import datetime

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ... import auth
from ...auth import get_db
from ...clients.ai_error import AIError
from ...database import models
from ...utils import ai_balances, ai_budget, ai_cost, ai_providers, ai_spend, ai_usage, ai_wallet, messages, settings
from .common import router


@router.get("/ai-usage")
def get_ai_usage(refresh: bool = False, provider: str = Query("openai", pattern="^(" + "|".join(ai_usage.ADMIN_KEYS) + ")$")):
    """The spend of the whole account of a provider since the app began, by month and by line item: what it billed, asked with its
    admin key (OpenAI by default, or Anthropic). It asks the provider (a blocking call: a plain def, so it runs in a worker thread)
    and keeps the answer a few minutes; `refresh` asks again. Without the key it says so, and whether the provider has a key for
    writing text at all (`provider_key`), so the panel shows the missing key only where it matters."""
    key = settings.get(ai_usage.ADMIN_KEYS[provider])
    if not key:
        return {"configured": False, "provider": provider, "provider_key": bool(ai_providers.api_key(provider))}
    try:
        data = ai_usage.summary(key, refresh=refresh, provider=provider)
    except AIError as e:
        raise HTTPException(status_code=502, detail=str(e).replace(key, "***"))
    return {"configured": True, "provider": provider, **data}


@router.get("/ai-usage/calls")
def get_ai_calls(month: str | None = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), db: Session = Depends(get_db)):
    """What the app's AI has been used for, from the record of its calls: totals, by whose key paid, by feature, model and
    kind of question, by player (only what the group's key paid for) and by month or, for a month, by day. The cost is an
    estimate (token prices of the day of each call)."""
    return {
        **ai_spend.summary(db, month),
        "retention_days": settings.get("ai.usage_retention_days"),
        "price_refresh_hours": settings.get("ai.price_refresh_hours"),
        "price_updates_running": ai_cost.updates_running(),
    }


@router.get("/ai-usage/budgets")
def get_ai_budgets(db: Session = Depends(get_db)):
    """The monthly budget of the group's key and each player's share of it, with what has been spent this month (only what the
    group's key paid: what a player pays with their own key never counts, nor is shown by name)."""
    spent = ai_budget.spent(db)
    return {
        "month": ai_budget.month_start().strftime("%Y-%m"),
        "resets_on": ai_budget.next_month().date().isoformat(),
        "group": {"cap": ai_budget.group_cap(), "spent": round(spent / ai_budget.MICROS, 6)},
        "unpriced": ai_budget.unpriced(db),  # what the caps cannot see: calls of a model with no price
        "default_user_cap": ai_budget.default_user_cap(),
        "players": ai_budget.players(db),
    }


class BudgetBody(BaseModel):
    # whole dollars a month of the group's key; 0 = nothing of it, null = back to the default of the settings (which may be no limit)
    usd: int | None = Field(default=None, ge=0, le=10000)


@router.put("/ai-usage/budgets/{user_id}")
def put_ai_budget(user_id: int, body: BudgetBody, db: Session = Depends(get_db)):
    """Gives a player another monthly budget of the group's key than the default (null goes back to the default). Like every
    write of the panel, it is in the audit log."""
    user = db.get(models.User, user_id)
    if user is None or user.username == models.GOD_USERNAME:
        raise HTTPException(status_code=404, detail=messages.USER_NOT_EXISTS)
    ai_budget.set_user_cap(db, user_id, body.usd)
    return next(p for p in ai_budget.players(db) if p["user_id"] == user_id)


@router.get("/ai-usage/wallet")
def get_ai_wallet(db: Session = Depends(get_db)):
    """The wallet of the group's key: what each player has put in, what the group's key has spent of it since it started and
    what is left (to set against the balance of the OpenAI account), and the latest contributions."""
    return ai_wallet.overview(db)


class WalletEntryBody(BaseModel):
    user_id: int
    # dollars put in (negative: a refund or a correction); two decimals are enough for a contribution
    usd: float = Field(ge=-ai_wallet.MAX_USD, le=ai_wallet.MAX_USD)
    note: str | None = Field(default=None, max_length=200)


@router.post("/ai-usage/wallet/entries", status_code=201)
def post_wallet_entry(body: WalletEntryBody, admin: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Writes down a contribution of a player to the wallet (or a refund, if negative). Entries are never edited: a mistake is
    corrected with another one. The first one switches the wallet on."""
    user = db.get(models.User, body.user_id)
    if user is None or user.username == models.GOD_USERNAME:
        raise HTTPException(status_code=404, detail=messages.USER_NOT_EXISTS)
    if round(body.usd * ai_wallet.MICROS) == 0:
        raise HTTPException(status_code=400, detail=messages.WALLET_AMOUNT_ZERO)
    ai_wallet.add(db, user.id, body.usd, body.note, admin.id)
    return ai_wallet.overview(db)


class WalletStartBody(BaseModel):
    # the day the wallet starts counting what the group's key spends; null goes back to the day of the first contribution
    date: datetime.date | None = None


@router.put("/ai-usage/wallet/start")
def put_wallet_start(body: WalletStartBody, admin: models.User = Depends(auth.get_current_active_user), db: Session = Depends(get_db)):
    """Chooses the day the wallet starts counting the spending (null: the day of the first contribution)."""
    settings.set_values(db, {"ai.wallet_start": body.date.isoformat() if body.date else None}, admin.id)
    return ai_wallet.overview(db)


@router.get("/ai-usage/balances")
def get_ai_balances(refresh: bool = False):
    """What the accounts of the group's keys really hold, for the providers that say it (OpenRouter), to set against the wallet. It
    asks the providers (a blocking call: a plain def, so it runs in a worker thread) and keeps the answer a few minutes; `refresh`
    asks again. A provider that fails comes with its error; the rest still answer."""
    return {"balances": ai_balances.summary(refresh)}
