"""What the AI has cost (OpenAI's billed spend)."""
from fastapi import HTTPException

from ...clients.ai_error import AIError
from ...utils import ai_usage, settings
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
