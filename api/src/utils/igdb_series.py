"""The series (sagas) of a game that has an IGDB id, asked to IGDB when the game's page opens and kept in memory for a day
(see outside_cache.py: nothing is stored in the database). When IGDB fails, or is not configured, the page has no saga from
here (utils/rawg_series.py is asked next for a game that also has a RAWG id)."""
import asyncio

from ..clients import igdb
from .logger import LogManager
from .outside_cache import OutsideCache

logger = LogManager().get_logger()

CACHE_SECONDS = 24 * 3600
FAILURE_SECONDS = 5 * 60

cache = OutsideCache(CACHE_SECONDS, FAILURE_SECONDS)  # igdb id -> the series, or None when IGDB failed


async def series_of(igdb_id: int) -> list[dict] | None:
    """The other games of the series an IGDB game belongs to (empty when it has none), or None when IGDB cannot be
    asked (not configured, error): the caller shows no saga from here."""
    if not igdb.configured():
        return None
    return await cache.get(igdb_id, lambda: _fetch(igdb_id))


async def _fetch(igdb_id: int) -> list[dict] | None:
    try:
        return await asyncio.to_thread(igdb.series_of, igdb_id)
    except Exception as e:
        logger.warning(f"Error fetching the series of IGDB game {igdb_id}: {e}")
        return None


def clear() -> None:
    """Forget everything (the tests)."""
    cache.clear()
