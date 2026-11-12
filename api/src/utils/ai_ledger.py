"""The record of what the AI is asked and what it costs (`ai_usage`): one row per call that a player made.

Everything is measured from the result of the agent run: the tokens, the tools it called (which says what kind of question
it was) and the web searches. The text of the question and of the answer is never stored, only how long the question was.
Writing a row is best effort: if it fails, the player still gets the answer and the failure goes to the log.

Nothing is cached here: the panels sum the rows when asked."""
import datetime
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..database import models
from . import ai_cost, settings
from .logger import LogManager

logger = LogManager().get_logger()

GROUP, USER = "group", "user"  # whose key paid
OK, OFF_TOPIC, TOO_BIG, QUOTA, ERROR, LIMITED, BUDGET = "ok", "off_topic", "too_big", "quota", "error", "limited", "budget"
SEARCH_TOOL = "web_search"  # the kind of pydantic-ai's WebSearchTool
OUTPUT_TOOL = "final_result"  # how pydantic-ai names the tool that carries a structured answer: not a lookup the model made
TOOLS_MAX = 255  # the column's length


@dataclass
class Spent:
    """What one call used, measured from the run's result."""

    provider: str | None = None
    model: str | None = None
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    requests: int = 0
    tool_calls: int = 0
    web_searches: int = 0
    latency_ms: int | None = None
    cost_micros: int | None = None
    tools: str | None = None


def tools_called(messages) -> tuple[list[str], int]:
    """The distinct tools the model called, in order, and how many web searches it made, from the messages of a run."""
    from pydantic_ai.messages import ModelResponse, NativeToolCallPart, ToolCallPart

    names: list[str] = []
    searches = 0
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, NativeToolCallPart) and part.tool_name == SEARCH_TOOL:
                searches += 1
                name = SEARCH_TOOL
            elif isinstance(part, ToolCallPart) and part.tool_name != OUTPUT_TOOL:
                name = part.tool_name
            else:
                continue
            if name not in names:
                names.append(name)
    return names, searches


def measure(result, provider: str | None, model: str | None, started: float, now: float) -> Spent:
    """What a finished run used. `started` and `now` are monotonic seconds. The cost is the tokens' at the prices of the
    moment (the web searches included), or None when the price of the model is not known."""
    usage = result.usage
    names, searches = tools_called(result.new_messages())
    cost = ai_cost.tokens_cost_micros(r for r in result.new_messages() if r.kind == "response")
    return Spent(
        provider=provider,
        model=model,
        input_tokens=usage.input_tokens or 0,
        cached_tokens=usage.cache_read_tokens or 0,
        output_tokens=usage.output_tokens or 0,
        reasoning_tokens=int((getattr(usage, "details", None) or {}).get("reasoning_tokens", 0) or 0),
        requests=usage.requests or 0,
        tool_calls=usage.tool_calls or 0,
        web_searches=searches,
        latency_ms=int((now - started) * 1000),
        cost_micros=cost,
        tools=",".join(names)[:TOOLS_MAX] or None,
    )


def record(
    db: Session,
    *,
    user_id: int | None,
    feature: str,
    key_source: str,
    status: str,
    spent: Spent | None = None,
    provider: str | None = None,
    model: str | None = None,
    question: str | None = None,
    turns: int | None = None,
    game_id: str | None = None,
) -> None:
    """Writes the row of one call. Never raises: what could not be written is logged, the answer goes on."""
    spent = spent or Spent(provider=provider, model=model)
    try:
        db.add(models.AiUsage(
            user_id=user_id,
            feature=feature,
            key_source=key_source,
            provider=spent.provider or provider,
            model=(spent.model or model or "")[:80] or None,
            status=status,
            input_tokens=spent.input_tokens,
            cached_tokens=spent.cached_tokens,
            output_tokens=spent.output_tokens,
            reasoning_tokens=spent.reasoning_tokens,
            requests=spent.requests,
            tool_calls=spent.tool_calls,
            web_searches=spent.web_searches,
            latency_ms=spent.latency_ms,
            cost_micros=spent.cost_micros,
            price_stamp=ai_cost.price_stamp() if spent.cost_micros is not None else None,
            tools=spent.tools,
            question_chars=min(len(question), 32767) if question is not None else None,
            turns=turns,
            game_id=game_id,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error writing the AI usage record: {type(e).__name__}: {e}", exc_info=True)


def purge(db: Session, now: datetime.datetime | None = None) -> int:
    """Deletes the rows older than `ai.usage_retention_days` (0 keeps them for ever). Returns how many."""
    days = settings.get("ai.usage_retention_days")
    if not days:
        return 0
    limit = (now or datetime.datetime.now()) - datetime.timedelta(days=days)
    deleted = db.execute(delete(models.AiUsage).where(models.AiUsage.created_at < limit)).rowcount
    db.commit()
    return deleted
