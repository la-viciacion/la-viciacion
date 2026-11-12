"""What the AI has cost: OpenAI's billed spend, and the calls the app made (what it used, who paid, the kind of question)."""
from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...auth import get_db
from ...clients.ai_error import AIError
from ...utils import ai_cost, ai_spend, ai_usage, settings
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
