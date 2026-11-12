"""What a call to the AI costs: the token prices of every model, kept up to date, not written in this code.

The prices come from `genai-prices` (the library pydantic-ai already uses): it carries a snapshot of them and, started
(`start_updates`), asks a public file once every `ai.price_refresh_hours` for newer ones and keeps them in memory. A
price that changes tomorrow does not change what a call cost today: the estimate is made when the call happens and
stored with the date of the prices it used (`ai_usage.price_stamp`). If the file cannot be fetched the snapshot goes
on, so nothing here can stop an answer. Only OpenAI's and Google's tokens are priced by the library; the web searches
are billed per call and apart, and the library prices them too, per model (`web_searches_kcount`): pydantic-ai counts them
on the usage of each response, so they are already in the cost of a response.

Neither provider offers an API with its price list, which is why a third party's file is used: it is what the estimate
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


def completion_cost_micros(provider: str | None, model: str | None, used) -> int | None:
    """The cost, in millionths of a dollar, of one completion of a notice from the tokens it used (the client left them in
    clients/used.py), or None if the price of its model is not known."""
    try:
        from genai_prices import Usage, calc_price

        found = calc_price(
            Usage(input_tokens=used.input_tokens, cache_read_tokens=used.cached_tokens, output_tokens=used.output_tokens),
            model, provider_id=provider,
        )
        return to_micros(found.total_price)
    except Exception:
        return None


def tokens_cost_micros(responses) -> int | None:
    """The cost, in millionths of a dollar, of the model responses of one call (their tokens and their web searches), or None
    if the price of a model is not known, or a response made searches that its model has no price for: a partial figure
    would hide that something was not counted."""
    total = Decimal(0)
    for response in responses:
        try:
            priced = response.cost()
            searched = getattr(response.usage, "web_searches", 0)
            if searched and not getattr(priced.model_price, "web_searches_kcount", None):
                return None
            total += Decimal(str(priced.total_price))
        except Exception:
            return None
    return to_micros(total)
