"""What a call to the AI costs: the token prices of every model, kept up to date, not written in this code.

The prices come from `genai-prices` (the library pydantic-ai already uses): it carries a snapshot of them and, started
(`start_updates`), asks a public file once every `ai.price_refresh_hours` for newer ones and keeps them in memory. A
price that changes tomorrow does not change what a call cost today: the estimate is made when the call happens and
stored with the date of the prices it used (`ai_usage.price_stamp`). If the file cannot be fetched the snapshot goes
on, so nothing here can stop an answer. The library prices the tokens of OpenAI, Google, Anthropic and the models of OpenRouter it
knows (OpenRouter itself says what it charged, which wins: `reported_cost`); the web searches are billed per call and apart, and the library prices them too, per model (`web_searches_kcount`): pydantic-ai counts them
on the usage of each response, so they are already in the cost of a response.

No provider offers an API with its price list, which is why a third party's file is used: it is what the estimate
rests on, and the panel says so. OpenAI's own billed spend (utils/ai_usage.py) is the figure to compare it with."""
import datetime
from decimal import Decimal

from . import settings
from .logger import LogManager

logger = LogManager().get_logger()

MICROS = 1_000_000
_updater = None


def start_updates() -> None:
    """Asks for newer prices every `ai.price_refresh_hours` (0: never, the snapshot the library came with is used). Quiet if
    the library cannot do it: a price list that is a little old is not worth an error."""
    global _updater
    hours = settings.get("ai.price_refresh_hours")
    if not hours or _updater is not None:
        return
    try:
        from genai_prices import UpdatePrices

        _updater = UpdatePrices(update_interval=hours * 3600)
        _updater.start()
    except Exception as e:
        _updater = None
        logger.warning(f"The AI prices will not be refreshed: {type(e).__name__}: {e}")


def updates_running() -> bool:
    return _updater is not None


def stop_updates() -> None:
    global _updater
    if _updater is not None:
        _updater.stop()
        _updater = None


def price_stamp() -> datetime.datetime | None:
    """When the prices in use were published, or None if they are the ones the library came with."""
    try:
        from genai_prices.data_snapshot import get_snapshot

        snapshot = get_snapshot()
        return snapshot.timestamp.replace(tzinfo=None) if snapshot.from_auto_update else None
    except Exception:
        return None


def to_micros(dollars) -> int:
    return int((Decimal(str(dollars)) * MICROS).to_integral_value())


def reported_cost(response) -> Decimal | None:
    """What OpenRouter itself says a response cost, web searches included, or None if the provider does not say (every other one).
    Its models go by many names that the price list does not know, and it knows what it charged: a call it reports with no cost
    (a free model) cost nothing."""
    details = getattr(response, "provider_details", None) or {}
    if getattr(response, "provider_name", None) != "openrouter" or not ("cost" in details or "is_byok" in details):
        return None
    return Decimal(str(details.get("cost") or 0))


def tokens_cost_micros(responses) -> int | None:
    """The cost, in millionths of a dollar, of the model responses of one call (their tokens and their web searches), or None
    if the price of a model is not known, or a response made searches that its model has no price for: a partial figure
    would hide that something was not counted. A provider that reports what it charged is believed (`reported_cost`)."""
    total = Decimal(0)
    for response in responses:
        reported = reported_cost(response)
        if reported is not None:
            total += reported
            continue
        try:
            priced = response.cost()
            searched = getattr(response.usage, "web_searches", 0)
            if searched and not getattr(priced.model_price, "web_searches_kcount", None):
                return None
            total += Decimal(str(priced.total_price))
        except Exception:
            return None
    return to_micros(total)
