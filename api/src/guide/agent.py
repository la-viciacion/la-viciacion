"""The game guide: a question about one game (plus a little history) in, one answer out.

It differs from the chat on purpose. The chat answers from the group's data through tools; the guide answers from the
web, so its one tool is the provider's own web search (OpenAI's through the Responses API, Google's search grounding,
Anthropic's web search tool, which its organization must have enabled, OpenRouter's web search server tool) and what the app
knows about the game and the player goes into the instructions, already read. With no function tools and a plain text answer
it works the same on all of them (Gemini refuses to mix its search with function tools).
The conversation lives in the client, like the chat's: nothing of it is stored."""
import datetime
import time
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits
from sqlalchemy.orm import Session

from ..chat import agent as chat_agent
from ..clients.ai_error import QuotaError
from ..chat.tools import hours
from ..utils import ai_ledger, ai_providers, messages, settings
from ..utils.logger import LogManager
from .prompt import DEFAULT_LEVEL, LEVELS

logger = LogManager().get_logger()

MAX_QUESTION = 500
MAX_HISTORY = chat_agent.MAX_HISTORY
# A search takes a while: more than the chat's 30 s, still a timeout and not patience
SETTINGS = ModelSettings(temperature=0.3, timeout=60, thinking=False)
LIMITS = UsageLimits(request_limit=6, total_tokens_limit=60_000)

# `openai` needs the Responses API for the web search (the chat completions one has none); the ids are the same as the chat's
BUILDERS = {
    "openai": lambda name, key: OpenAIResponsesModel(name, provider=OpenAIProvider(api_key=key)),
    "google": lambda name, key: GoogleModel(name, provider=GoogleProvider(api_key=key)),
    "anthropic": lambda name, key: AnthropicModel(name, provider=AnthropicProvider(api_key=key)),
    "openrouter": lambda name, key: OpenRouterModel(name, provider=OpenRouterProvider(api_key=key)),
}


@dataclass
class GuideDeps:
    game: str  # what the app knows about the game and the player, as text (game_context)
    level: str
    user_name: str
    # what the usage record needs (utils/ai_ledger.py); without a session nothing is recorded (the probe, the tests)
    db: Session | None = None
    user_id: int | None = None
    game_id: str | None = None
    source: object | None = None  # whose key pays (utils/ai_source.py Source); the group's when none


def build_model(source=None) -> Model:
    """The model for a source of key (utils/ai_source.py): the player's own, or the group's when none is given."""
    if source is not None:
        return BUILDERS[source.provider](source.model, source.api_key)
    provider, key, name = ai_providers.group_credentials(ai_providers.GUIDE)
    return BUILDERS[provider](name, key)


def is_ready() -> bool:
    return bool(settings.get("guide.enabled") and configured())


def configured() -> bool:
    """There is a provider with a key and a model for the guide (whether it is switched on or not)."""
    return ai_providers.group_credentials(ai_providers.GUIDE) is not None


def game_context(data: dict) -> str:
    """What the app knows about the game and the player who asks (the game page's overview, pure): enough for the model to
    place them (how long they have played, whether they finished it, who in the group did) and nothing it has to look up."""
    game, summary = data["game"], data["summary"]
    lines = [f"Juego: {game['name']}"]
    if game.get("release_date"):
        released = game["release_date"]
        lines.append(f"Salida: {released.isoformat() if isinstance(released, (datetime.date, datetime.datetime)) else released}")
    for label, key in (("Géneros", "genres"), ("Desarrolladora", "dev")):
        value = game.get(key)
        if value:
            lines.append(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    if game.get("avg_time"):
        lines.append(f"Duración media para terminarlo: {hours(game['avg_time'])} h")
    mine = next((p for p in data["players"] if p["is_me"]), None)
    if mine is None:
        lines.append("La persona no lo tiene en su biblioteca.")
    else:
        status = "ya lo ha completado" if mine["completed"] else "todavía no lo ha completado"
        lines.append(f"La persona lleva {hours(mine['played_seconds'])} h en {mine['sessions']} sesiones y {status}.")
    done = [p["name"] for p in data["players"] if p["completed"] and not p["is_me"]][:5]
    if done:
        lines.append(f"Del grupo lo han completado: {', '.join(done)} ({summary['completed_by']} en total).")
    return "\n".join(lines)


agent = Agent(output_type=str, deps_type=GuideDeps, retries=1, model_settings=SETTINGS, capabilities=[NativeTool(WebSearchTool())])


@agent.instructions
def instructions(ctx: RunContext[GuideDeps]) -> str:
    level = LEVELS.get(ctx.deps.level, LEVELS[DEFAULT_LEVEL])
    return (
        settings.get("guide.prompt")
        + f"\n\nHoy es {datetime.date.today().isoformat()}. Hablas con {ctx.deps.user_name}."
        + f"\n\nNivel de ayuda: {level}"
        + f"\n\nLo que sabe la app:\n{ctx.deps.game}"
    )


def ask(deps: GuideDeps, question: str, history: list[tuple[str, str]], model=None) -> str:
    """Blocking: call it from a worker thread. Raises AIError if the provider fails. `model` is for the tests. Every outcome
    leaves a row in the AI usage record, with the numbers and never the text."""
    started = time.monotonic()
    source = deps.source
    if source is not None:
        provider, name = source.provider, source.model
    else:
        provider, name = ai_providers.current(ai_providers.GUIDE) if deps.db is not None else (None, None)
    paid_by = source.key_source if source is not None else ai_ledger.GROUP
    recorded = dict(user_id=deps.user_id, feature="guide", key_source=paid_by, question=question, turns=len(history), game_id=deps.game_id, provider=provider, model=name)

    def record(status, **more):
        if deps.db is not None:
            ai_ledger.record(deps.db, status=status, **recorded, **more)

    try:
        result = agent.run_sync(
            question,
            deps=deps,
            model=model or build_model(source),
            message_history=chat_agent.history_messages(history),
            usage_limits=LIMITS,
        )
    except UsageLimitExceeded as e:
        logger.warning(f"Guide question stopped by a usage limit: {e}")
        record(ai_ledger.TOO_BIG)
        return messages.CHAT_TOO_COMPLEX
    except Exception as e:
        error = chat_agent.failure(e, "guide", chat_agent.own_key(source), ai_providers.GUIDE)
        record(ai_ledger.QUOTA if isinstance(error, QuotaError) else ai_ledger.ERROR)
        raise error from None
    used = result.usage
    logger.info(
        f"Guide question answered in {time.monotonic() - started:.1f} s: {used.requests} model requests, "
        f"{used.input_tokens} tokens in and {used.output_tokens} out"
    )
    if deps.db is not None:
        record(ai_ledger.OK, spent=ai_ledger.measure(result, provider, name, started, time.monotonic()))
    return result.output.strip()


def probe(model=None, source=None, user_id: int | None = None) -> str:
    """One answer that needs the web (who made a game that came out a year ago), for the panel's test button: it fails, with
    the provider's own words, when the model cannot search. Blocking, like `ask`. Raises AIError if the provider fails. It spends
    a key, so it leaves a row in the usage record: the group's, or the player's own (`source`, with their `user_id`)."""
    started = time.monotonic()
    provider, name = (source.provider, source.model) if source is not None else ai_providers.current(ai_providers.GUIDE)
    paid_by = source.key_source if source is not None else ai_ledger.GROUP
    deps = GuideDeps(game="Juego: Hollow Knight", level="hint", user_name="el admin")
    try:
        result = agent.run_sync(
            "Busca en la web quién desarrolló este juego y responde en una frase, citando la fuente.",
            deps=deps, model=model or build_model(source), usage_limits=LIMITS,
        )
    except Exception as e:
        error = chat_agent.failure(e, "guide_test", chat_agent.own_key(source), ai_providers.GUIDE)
        ai_ledger.record_probe("guide_test", provider, name, ai_ledger.QUOTA if isinstance(error, QuotaError) else ai_ledger.ERROR, started, key_source=paid_by, user_id=user_id)
        raise error from None
    ai_ledger.record_probe("guide_test", provider, name, ai_ledger.OK, started, result, key_source=paid_by, user_id=user_id)
    return result.output.strip()
