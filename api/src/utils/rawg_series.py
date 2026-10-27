"""The series (sagas) of a game, asked to RAWG when a game's page opens and kept in memory for a day (see
outside_cache.py: nothing is stored in the database). When RAWG fails, or there is no key, the page simply has no saga."""
from ..config import Config
from . import my_utils
from .logger import LogManager
from .outside_cache import OutsideCache
from .redaction import redact_rawg_key

logger = LogManager().get_logger()
config = Config()

CACHE_SECONDS = 24 * 3600
FAILURE_SECONDS = 5 * 60
PAGE_SIZE = 40  # RAWG's default is 20

cache = OutsideCache(CACHE_SECONDS, FAILURE_SECONDS)  # rawg id -> the series, or None when RAWG failed


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


async def series_of(rawg_id: int) -> list[dict] | None:
    """The other games of the series a RAWG game belongs to (empty when it has none), or None when RAWG cannot be
    asked (no key, error): the caller shows no saga then."""
    if not config.RAWG_API_KEY:
        return None
    return await cache.get(rawg_id, lambda: _fetch(rawg_id))


async def _fetch(rawg_id: int) -> list[dict] | None:
    try:
        resp = await my_utils._http_get(
            f"https://api.rawg.io/api/games/{rawg_id}/game-series", {"key": config.RAWG_API_KEY, "page_size": PAGE_SIZE}, timeout=8
        )
        if not resp.ok:
            logger.warning(f"RAWG series error {resp.status_code} for game {rawg_id}: {redact_rawg_key(resp.content)}")
            return None
        return parse(resp.json().get("results"))
    except Exception as e:
        logger.warning(f"Error fetching the series of RAWG game {rawg_id}: {redact_rawg_key(e)}")
        return None


def clear() -> None:
    """Forget everything (the tests, and anybody who changes the key)."""
    cache.clear()
