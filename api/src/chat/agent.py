"""The chat agent: one question (plus a little history) in, one answer out.

The scope is limited three ways: the instructions (the admin's `chat.prompt`), the tools (read-only, see
tools.py) and hard caps on what one question may cost (UsageLimits, a timeout). The answer is structured so the
code, not only the prompt, knows when a question was out of scope."""
import datetime
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session

from ..clients.ai_error import AIError, QuotaError
from ..clients.quota import classify
from ..database import models
from ..utils import ai_quota, messages, seasons, settings
from ..utils.logger import LogManager
from . import model as chat_model
from .limits import LIMITS, MAX_HISTORY
from .tools import TOOLS, ChatDeps

logger = LogManager().get_logger()

# A question is answered from what the tools return, so the model has nothing to think over: with its reasoning on, a plain
# question took 40 to 48 s. `thinking=False` turns it off (the lowest level on a model that cannot be turned off) and is
# ignored by a model that does not reason, whatever the provider.
# A request that takes longer than the timeout is a failure, not patience.
SETTINGS = ModelSettings(temperature=0.3, timeout=30, thinking=False)


class Reply(BaseModel):
    in_scope: bool = Field(description="False when the question is not about video games or the app's data")
    answer: str = Field(description="The answer, in Spanish, short")


@dataclass
class Answer:
    text: str
    in_scope: bool


agent = Agent(output_type=Reply, deps_type=ChatDeps, tools=TOOLS, retries=2, model_settings=SETTINGS)


@agent.instructions
def instructions(ctx: RunContext[ChatDeps]) -> str:
    name = ctx.deps.user.name or ctx.deps.user.username
    return (
        settings.get("chat.prompt")
        + f"\n\nHoy es {datetime.date.today().isoformat()} y la temporada actual es {seasons.current()}."
        + f" Hablas con {name}; cuando diga 'yo' o 'mi', se refiere a esa persona."
    )


def history_messages(history: list[tuple[str, str]]) -> list[ModelMessage]:
    """The conversation so far ((role, text), role 'user' or 'assistant') as the model's messages: the last MAX_HISTORY,
    starting with a question (a provider may refuse a conversation that starts with an answer)."""
    recent = history[-MAX_HISTORY:]
    while recent and recent[0][0] != "user":
        recent = recent[1:]
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]) if role == "user" else ModelResponse(parts=[TextPart(content=text)])
        for role, text in recent
    ]


def failure(e: Exception, source: str) -> AIError:
    """What a provider failure becomes: a QuotaError (also written to the audit log) if a quota ran out, else an AIError
    whose message never carries the key."""
    quota = classify(e)
    if quota:
        ai_quota.report(quota, source, settings.get("ai.provider"), chat_model.model_name())
        return QuotaError(f"chat: {quota.describe()}", quota)
    # a provider library may quote what it was given: never let the key out in the message
    return AIError(f"chat: {type(e).__name__}: {str(e).replace(settings.get('ai.api_key') or chr(0), '***')}")


def ask(db: Session, user: models.User, question: str, history: list[tuple[str, str]], model=None) -> Answer:
    """Blocking: call it from a worker thread. Raises AIError if the provider fails. `model` is for the tests."""
    started = time.monotonic()
    try:
        result = agent.run_sync(
            question,
            deps=ChatDeps(db=db, user=user),
            model=model or chat_model.build_model(),
            message_history=history_messages(history),
            usage_limits=LIMITS,
        )
    except UsageLimitExceeded as e:
        # which limit it was is what tells whether a question is too big or a limit too tight
        logger.warning(f"Chat question stopped by a usage limit: {e}")
        return Answer(messages.CHAT_TOO_COMPLEX, True)
    except Exception as e:
        raise failure(e, "chat") from None
    used = result.usage
    logger.info(
        f"Chat question answered in {time.monotonic() - started:.1f} s: {used.requests} model requests, {used.tool_calls} tool calls, "
        f"{used.input_tokens} tokens in and {used.output_tokens} out"
    )
    reply = result.output
    return Answer(reply.answer.strip() if reply.in_scope else messages.CHAT_OFF_TOPIC, reply.in_scope)


def probe(model=None) -> str:
    """One short sentence from the chat's model, with no tools: for the panel's test button (blocking, like `ask`).
    Raises AIError if the provider fails."""
    try:
        result = Agent(model or chat_model.build_model(), model_settings=SETTINGS).run_sync(
            "Saluda al grupo con una frase corta y divertida sobre videojuegos.", usage_limits=LIMITS
        )
    except Exception as e:
        raise failure(e, "chat_test") from None
    return result.output.strip()
