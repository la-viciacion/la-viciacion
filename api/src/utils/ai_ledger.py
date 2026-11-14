"""The record of what the AI is asked and what it costs (`ai_usage`): one row per call that a player made.

Everything is measured from the result of the agent run: the tokens, the tools it called (which says what kind of question
it was) and the web searches. The text of the question and of the answer is never stored, only how long the question was.
Writing a row is best effort: if it fails, the player still gets the answer and the failure goes to the log.

Nothing is cached here: the panels sum the rows when asked."""
import datetime
import time
from dataclasses import dataclass, replace

from sqlalchemy import case, delete
from sqlalchemy.orm import Session

from ..database import models
from . import ai_cost, settings
from .logger import LogManager

logger = LogManager().get_logger()

GROUP, USER = "group", "user"  # whose key paid
OK, OFF_TOPIC, TOO_BIG, QUOTA, ERROR, LIMITED, BUDGET = "ok", "off_topic", "too_big", "quota", "error", "limited", "budget"
BLOCKED_EVERY = datetime.timedelta(minutes=1)  # a player who is stopped and keeps asking leaves one row a minute, not one a request
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
        before = searches
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
        reported = reported_searches(message) if searches == before else 0  # a search seen as a tool call is not counted again
        if reported:
            searches += reported
            if SEARCH_TOOL not in names:
                names.append(SEARCH_TOOL)
    return names, searches


def reported_searches(response) -> int:
    """The web searches a provider says it ran itself, which leave no tool call in the messages: OpenRouter reports them in the
    usage of the answer (`server_tool_use.web_search_requests`) and charges them (ai_cost.reported_cost)."""
    used = (getattr(response, "provider_details", None) or {}).get("server_tool_use")
    return int(used.get("web_search_requests") or 0) if isinstance(used, dict) else 0


def measure(result, provider: str | None, model: str | None, started: float, now: float) -> Spent:
    """What a finished run used. `started` and `now` are monotonic seconds. The cost is the tokens' at the prices of the
    moment (the web searches included), or None when the price of the model is not known. It never raises: if the result
    cannot be read (a library that changed its shape) the call is still recorded, with no tokens, and the failure is logged,
    because the player's answer is already paid for and must not be lost to its own bookkeeping."""
    try:
        return _measure(result, provider, model, started, now)
    except Exception as e:
        logger.error(f"Error measuring the usage of an AI call: {type(e).__name__}: {e}", exc_info=True)
        return Spent(provider=provider, model=model, latency_ms=int((now - started) * 1000))


def _measure(result, provider: str | None, model: str | None, started: float, now: float) -> Spent:
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


def free_plan(provider: str | None, key_source: str) -> bool:
    """Whether a call was paid by a key of the group that is on a free plan (admin setting `ai.free_plan.<provider>`): its real cost
    is nothing, whatever its estimate says. A player's own key is never on one."""
    name = f"ai.free_plan.{provider}"
    if key_source != GROUP or name not in settings.REGISTRY:
        return False
    try:
        return bool(settings.get(name))
    except Exception as e:  # the setting is not worth losing the row of a call that was already paid for: it counts at its estimate
        logger.error(f"Error reading {name} to record an AI call: {type(e).__name__}: {e}")
        return False


def real_cost():
    """The SQL expression of what a call really cost, in millionths of a dollar: its estimate, or 0 when it was on a free plan."""
    return case((models.AiUsage.free_plan.is_(True), 0), else_=models.AiUsage.cost_micros)


def record_blocked(db: Session, *, user_id: int, feature: str, **fields) -> None:
    """Writes the row of a question the group's key was not allowed to pay for (status `budget`), unless this player already has one
    for this feature in the last minute: the row is there to show the demand that was stopped, not to count every retry."""
    since = datetime.datetime.now() - BLOCKED_EVERY
    recent = db.query(models.AiUsage.id).filter(
        models.AiUsage.user_id == user_id, models.AiUsage.feature == feature,
        models.AiUsage.status == BUDGET, models.AiUsage.created_at >= since,
    ).first()
    if recent is None:
        record(db, user_id=user_id, feature=feature, key_source=GROUP, status=BUDGET, **fields)


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
            free_plan=free_plan(spent.provider or provider, key_source),
            tools=spent.tools,
            question_chars=min(len(question), 32767) if question is not None else None,
            turns=turns,
            game_id=game_id,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error writing the AI usage record: {type(e).__name__}: {e}", exc_info=True)


TEST = "test"  # the feature of what an admin's or a player's test button asks: it spends real tokens, so it is recorded
TEST_KINDS = ("ai_test", "chat_test", "guide_test")


def notice_kind(source: str) -> tuple[str, str | None] | None:
    """(feature, kind) of a text the AI writes on its own, from who asked (`ai.complete`'s `source`): the welcome of the group,
    a notice (`notice:completed_game`: its kind is the part after the colon) or a test button of the panel. Every use of the AI
    is recorded: None only for a source this does not know."""
    if source == "welcome":
        return "welcome", "welcome"
    if source == "notice" or source.startswith("notice:"):
        return "notice", source.partition(":")[2] or None
    if source in TEST_KINDS:
        return TEST, source
    return None


def _record_alone(feature: str, status: str, spent: Spent, key_source: str = GROUP, user_id: int | None = None) -> None:
    """Writes a row from a worker thread that has no session of its own (a notice, a test button). Never raises, like `record`."""
    try:
        db = open_session()
    except Exception as e:
        logger.error(f"Error opening a session for the AI usage record: {type(e).__name__}: {e}", exc_info=True)
        return
    try:
        record(db, user_id=user_id, feature=feature, key_source=key_source, status=status, spent=spent)
    finally:
        db.close()


def waited(started: float) -> Spent:
    """What is known of a call that failed before it said anything about its tokens: that it was made, and how long it took."""
    return Spent(requests=1, latency_ms=int((time.monotonic() - started) * 1000))


def _spent_of(kind: str | None, provider: str | None, model: str | None, started: float, result) -> Spent:
    """What an agent run that is recorded apart from a player's question used (`result` is the run's, None when it failed), with
    the kind of text it was."""
    now = time.monotonic()
    if result is None:
        return Spent(provider=provider, model=model, latency_ms=int((now - started) * 1000), tools=kind)
    return replace(measure(result, provider, model, started, now), tools=kind)


def record_notice(source: str, provider: str | None, model: str | None, status: str, started: float, result=None) -> None:
    """Writes the row of a text the AI wrote on its own (a notice, the group's welcome, the admin's test of the notices): no
    player asked for it, so it has no user, and the group's key paid. It runs in the worker thread that asked the provider, so it
    opens its own session. Never raises, like `record`. `result` is the run's, None when it failed."""
    found = notice_kind(source)
    if found is None:
        return
    feature, kind = found
    spent = _spent_of(kind, provider, model, started, result)
    _record_alone(feature, status, spent if result is not None else replace(spent, requests=1))  # a failed notice was asked all the same


def record_probe(kind: str, provider: str | None, model: str | None, status: str, started: float, result=None, key_source: str = GROUP, user_id: int | None = None) -> None:
    """Writes the row of a test button that runs an agent (the chat's and the guide's): `result` is the run's, None when it
    failed. A player's own test (`key_source` user, with their `user_id`) is in their record and never in the group's spending."""
    _record_alone(TEST, status, _spent_of(kind, provider, model, started, result), key_source, user_id)


def open_session() -> Session:
    from ..database.database import SessionLocal

    return SessionLocal()


def purge(db: Session, now: datetime.datetime | None = None) -> int:
    """Deletes the rows older than `ai.usage_retention_days` (0 keeps them for ever). Returns how many."""
    days = settings.get("ai.usage_retention_days")
    if not days:
        return 0
    limit = (now or datetime.datetime.now()) - datetime.timedelta(days=days)
    deleted = db.execute(delete(models.AiUsage).where(models.AiUsage.created_at < limit)).rowcount
    db.commit()
    return deleted
