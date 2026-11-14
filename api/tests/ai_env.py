"""The settings the AI reads (utils/ai_providers.py) as a test double of `settings.get`: one provider with its key and model, the
rest of the providers without a key and no model picked in the panel."""
import contextlib
from unittest import mock

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from src.utils import ai, ai_build, settings


def group(provider: str | None = "openai", key: str | None = "KEY", model: str | None = "m", chat_model: str | None = None, **overrides) -> dict:
    table = {"ai.provider": provider, "chat.provider": None, "guide.provider": None}
    for p in settings.AI_PROVIDERS:
        table.update({f"ai.{p}.api_key": None, f"ai.{p}.model": None, f"ai.{p}.chat_model": None, f"ai.model.{p}": None, f"chat.model.{p}": None, f"guide.model.{p}": None})
    if provider:
        table.update({f"ai.{provider}.api_key": key, f"ai.{provider}.model": model, f"ai.{provider}.chat_model": chat_model})
    return {**table, **overrides}


def says(text: str = "Hola", input_tokens: int = 0, output_tokens: int = 0, seen: list | None = None, model: str = "gpt-4.1-mini", provider: str = "openai", **response) -> FunctionModel:
    """A model that answers `text` and reports those tokens, as `provider`'s `model` (what its price is read from). What it was asked
    (the messages and the settings) is appended to `seen`; `response` is more of the model's answer (`finish_reason`, `provider_details`)."""
    def respond(messages, info):
        if seen is not None:
            seen.append((messages, info.model_settings))
        return ModelResponse(parts=[TextPart(text)], usage=RequestUsage(input_tokens=input_tokens, output_tokens=output_tokens), provider_name=provider, **response)

    return FunctionModel(respond, model_name=model)


def fails(error: BaseException) -> FunctionModel:
    """A model whose provider fails with `error`."""
    def respond(messages, info):
        raise error

    return FunctionModel(respond)


@contextlib.contextmanager
def using(model):
    """Makes the model the one `ai_build.build` gives (what `ai.complete` asks for): the notices talk to it instead of a provider.
    Yields the patched `build`. The notices keep the group's model between calls, so it is forgotten on the way in and out."""
    ai._group_model.cache_clear()
    try:
        with mock.patch.object(ai_build, "build", return_value=model) as build:
            yield build
    finally:
        ai._group_model.cache_clear()


FAST_KDF = {"n": 2**8, "r": 8, "p": 1}  # the tests do not need the real cost of an attacker


def give_key(db, user_id, key, model, provider="openai", password="Una-Contrasena-Muy-Larga-1!"):
    """Gives a player a key of their own the way the app does: their vault (made with `password`) and the key sealed in it. Returns the data
    key a session of theirs would carry, which is what `ai_source.decide` and the routes take."""
    from src.utils import ai_vault, user_ai

    with mock.patch.object(ai_vault, "KDF", FAST_KDF):
        dek = user_ai.unlock(db, user_id, password)
    user_ai.save(db, user_id, dek, provider, key, model)
    return dek


def free_wallet(db, *user_ids: int) -> None:
    """Gives the players (default: the first two of `seed`) a balance in the wallet that no test spends: the wallet is always on and a
    player starts with 0, so a test about anything else than the wallet starts from players the wallet does not stop."""
    import datetime

    from src.database import models

    for user_id in user_ids or (1, 2):
        db.add(models.AiWalletEntry(user_id=user_id, amount_micros=10**12, created_at=datetime.datetime(2020, 1, 1)))
    db.commit()
