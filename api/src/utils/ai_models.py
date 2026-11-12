"""The models a player can choose for their own key, with what each costs.

OpenAI lists everything a key can use (embeddings, audio, images...): only the ones that answer a chat are offered, without
the dated copies of a model (`gpt-4.1-mini-2025-04-14`). Each carries its price per million tokens from the same list as the
cost estimates (utils/ai_cost.py) and a tier read from it, so the player sees how much a model weighs on their account. It
is only a hint: the model is their decision, and an unknown one is accepted."""
import re
from decimal import Decimal

from . import user_ai

CHAT_MODEL = re.compile(r"^(gpt-|chatgpt-|o\d)")
NOT_FOR_CHAT = ("audio", "realtime", "transcribe", "tts", "image", "instruct", "embedding", "moderation", "search", "whisper", "dall-e", "codex", "computer-use", "deep-research")
DATED = re.compile(r"-\d{4}-\d{2}-\d{2}$|-\d{4}$")
ECONOMIC, MEDIUM, EXPENSIVE, UNPRICED = "economico", "medio", "caro", "sin_precio"
ECONOMIC_MAX, MEDIUM_MAX = Decimal(2), Decimal(12)  # dollars per million output tokens
MICRO = Decimal(1_000_000)


def for_chat(ids: list[str]) -> list[str]:
    return sorted(i for i in ids if CHAT_MODEL.match(i) and not DATED.search(i) and not any(word in i for word in NOT_FOR_CHAT) and user_ai.clean_model(i))


def prices(model: str) -> tuple[Decimal, Decimal] | None:
    """(dollars per million input tokens, per million output tokens) of an OpenAI model, or None if the list has none."""
    try:
        from genai_prices import Usage, calc_price

        cost = lambda usage: calc_price(Usage(**usage), model, provider_id=user_ai.PROVIDER).total_price  # noqa: E731
        return Decimal(str(cost({"input_tokens": MICRO}))), Decimal(str(cost({"output_tokens": MICRO})))
    except Exception:
        return None


def tier(output_price: Decimal | None) -> str:
    if output_price is None:
        return UNPRICED
    return ECONOMIC if output_price <= ECONOMIC_MAX else MEDIUM if output_price <= MEDIUM_MAX else EXPENSIVE


def describe(ids: list[str]) -> list[dict]:
    """The models to offer, each with its tier and its prices in dollars per million tokens (None without a price)."""
    out = []
    for model in for_chat(ids):
        found = prices(model)
        out.append({
            "id": model,
            "tier": tier(found[1] if found else None),
            "input_per_million": float(found[0]) if found else None,
            "output_per_million": float(found[1]) if found else None,
        })
    return out
