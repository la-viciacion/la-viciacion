"""The series (sagas) of a game, asked to RAWG when a game's page opens and kept in memory for a day.

Nothing is stored in the database: a series is outside data that changes rarely, so each worker keeps the answers it got
for CACHE_SECONDS (and forgets them when it restarts). When RAWG fails, or there is no key, the page simply has no saga:
the failure is remembered for a few minutes so a page that is opened again and again does not ask it every time."""
import asyncio
import time

from ..config import Config
from . import my_utils
from .logger import LogManager
from .redaction import redact_rawg_key

logger = LogManager().get_logger()
config = Config()

CACHE_SECONDS = 24 * 3600
FAILURE_SECONDS = 5 * 60
MAX_CACHED = 500  # games kept; the one that expires first goes when there are more
PAGE_SIZE = 40  # RAWG's default is 20

_cache: dict[int, tuple[float, list[dict] | None]] = {}  # rawg id -> (when it expires, the series or None if RAWG failed)
_asking: dict[int, asyncio.Task] = {}  # rawg id -> the answer being fetched, so a burst of requests asks RAWG once


def parse(results) -> list[dict]:
    """The games of a RAWG answer as the app uses them (RAWG sends explicit nulls for some fields)."""
    series = []
    for item in results or []:
        if not item.get("id") or not item.get("name"):
            continue
        series.append({
            "rawg_id": item["id"],
            "name": item["name"],
            "slug": item.get("slug") or None,
            "image_url": item.get("background_image") or None,
            "released": item.get("released") or None,
        })
    return series


def _remember(rawg_id: int, value: list[dict] | None, seconds: float) -> None:
    if len(_cache) >= MAX_CACHED:
        del _cache[min(_cache, key=lambda key: _cache[key][0])]
    _cache[rawg_id] = (time.time() + seconds, value)


async def series_of(rawg_id: int) -> list[dict] | None:
    """The other games of the series a RAWG game belongs to (empty when it has none), or None when RAWG cannot be
    asked (no key, error): the caller shows no saga then."""
    if not config.RAWG_API_KEY:
        return None
    cached = _cache.get(rawg_id)
    if cached and cached[0] > time.time():
        return cached[1]
    if rawg_id not in _asking:
        _asking[rawg_id] = asyncio.create_task(_fetch_once(rawg_id))
    return await asyncio.shield(_asking[rawg_id])  # shielded: a caller that goes away does not cancel the others' answer


async def _fetch_once(rawg_id: int) -> list[dict] | None:
    try:
        return await _fetch(rawg_id)
    finally:
        del _asking[rawg_id]


async def _fetch(rawg_id: int) -> list[dict] | None:
    try:
        resp = await my_utils._http_get(
            f"https://api.rawg.io/api/games/{rawg_id}/game-series", {"key": config.RAWG_API_KEY, "page_size": PAGE_SIZE}, timeout=8
        )
        if not resp.ok:
            logger.warning(f"RAWG series error {resp.status_code} for game {rawg_id}: {redact_rawg_key(resp.content)}")
            _remember(rawg_id, None, FAILURE_SECONDS)
            return None
        series = parse(resp.json().get("results"))
    except Exception as e:
        logger.warning(f"Error fetching the series of RAWG game {rawg_id}: {redact_rawg_key(e)}")
        _remember(rawg_id, None, FAILURE_SECONDS)
        return None
    _remember(rawg_id, series, CACHE_SECONDS)
    return series


def clear() -> None:
    """Forget everything (the tests, and anybody who changes the key)."""
    _cache.clear()
