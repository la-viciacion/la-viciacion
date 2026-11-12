"""What the AI has cost: OpenAI's billed spend, and the calls the app made (what it used, who paid, the kind of question)."""
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...auth import get_db
from ...clients.ai_error import AIError
from ...database import models
from ...utils import ai_budget, ai_cost, ai_spend, ai_usage, messages, settings
from .common import router


@router.get("/ai-usage")
def get_ai_usage(refresh: bool = False):
    """The spend of the whole account since the app began, by month and by line item. It asks OpenAI (a blocking call: a
    plain def, so it runs in a worker thread) and keeps the answer a few minutes; `refresh` asks again."""
    key = settings.get("ai.openai_admin_key")
    if not key:
        return {"configured": False}
    try:
        data = ai_usage.summary(key, refresh=refresh)
    except AIError as e:
        raise HTTPException(status_code=502, detail=str(e).replace(key, "***"))
    return {"configured": True, "provider": "openai", **data}


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
        "default_user_cap": int(settings.get("ai.user_budget_month") or 0),
        "players": ai_budget.players(db),
    }


class BudgetBody(BaseModel):
    # whole dollars a month of the group's key; 0 = no limit, null = back to the default of the settings
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
