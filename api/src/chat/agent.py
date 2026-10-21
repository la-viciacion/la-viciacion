"""The chat agent: one question (plus a little history) in, one answer out.

The scope is limited three ways: the instructions (the admin's `ai.prompt.chat`), the tools (read-only, see
tools.py) and hard caps on what one question may cost (UsageLimits, a timeout). The answer is structured so the
code, not only the prompt, knows when a question was out of scope."""
import datetime
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits
from sqlalchemy.orm import Session

from ..clients.ai_error import AIError
from ..database import models
from ..utils import messages, seasons, settings
from . import model as chat_model
from .tools import TOOLS, ChatDeps

MAX_HISTORY = 10  # messages of the conversation the model sees: older ones are dropped
LIMITS = UsageLimits(request_limit=8, tool_calls_limit=8, output_tokens_limit=1500)
SETTINGS = ModelSettings(temperature=0.3, timeout=30)  # a chat answer that takes longer is a failure, not patience


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
        settings.get("ai.prompt.chat")
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


def ask(db: Session, user: models.User, question: str, history: list[tuple[str, str]], model=None) -> Answer:
    """Blocking: call it from a worker thread. Raises AIError if the provider fails. `model` is for the tests."""
    key = settings.get("ai.api_key")
    try:
        result = agent.run_sync(
            question,
            deps=ChatDeps(db=db, user=user),
            model=model or chat_model.build_model(),
            message_history=history_messages(history),
            usage_limits=LIMITS,
        )
    except UsageLimitExceeded:
        return Answer(messages.CHAT_TOO_COMPLEX, True)
    except Exception as e:
        # a provider library may quote what it was given: never let the key out in the message
        raise AIError(f"chat: {type(e).__name__}: {str(e).replace(key or chr(0), '***')}") from None
    reply = result.output
    return Answer(reply.answer.strip() if reply.in_scope else messages.CHAT_OFF_TOPIC, reply.in_scope)
