"""What the world outside says about a game (a trailer, screenshots, a description, Metacritic, the age rating, the
publisher and the platforms it came out on), asked to Steam and RAWG when a game's page opens and kept in memory for a day
(see outside_cache.py: nothing is stored in the database).

It is all optional: Steam knows only the games that have a Steam app id (the game's `steam_id`, or the one RAWG's stores
link to when it has none) and RAWG the ones with a `rawg_id`, so a game from Nintendo gets only what RAWG has, and when
neither answers the page simply has no card. The description is Steam's, in Spanish; without it RAWG's, in English.
Prices are left out on purpose: they depend on the store, and a game is played on several platforms."""
import asyncio
import html
import re
from urllib.parse import urlparse

from ..config import Config
from . import my_utils
from .logger import LogManager
from .outside_cache import OutsideCache, Partial
from .redaction import redact_rawg_key

logger = LogManager().get_logger()
config = Config()

CACHE_SECONDS = 24 * 3600
FAILURE_SECONDS = 5 * 60
MAX_SCREENSHOTS = 8
MAX_PLATFORMS = 10
MEDIA_HOSTS = ("steamstatic.com", "akamaihd.net", "rawg.io")  # where the videos and pictures may come from

STEAM_MOVIE = "https://cdn.akamai.steamstatic.com/steam/apps/{movie_id}/movie480.mp4"  # what a plain <video> can play
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"
RAWG_GAME = "https://api.rawg.io/api/games/{rawg_id}"

cache = OutsideCache(CACHE_SECONDS, FAILURE_SECONDS)  # (rawg id, steam id) -> the extras, or None when nothing answered


def media_url(url) -> str | None:
    """`url` as https when it is on a host the app trusts for media, else None (the front puts it in a video or an image)."""
    if not isinstance(url, str):
        return None
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if parsed.scheme not in ("http", "https") or not any(host == h or host.endswith("." + h) for h in MEDIA_HOSTS):
        return None
    return parsed._replace(scheme="https").geturl()


def clean_text(text) -> str | None:
    """Plain text from the little HTML a store description may carry; None when nothing is left."""
    if not isinstance(text, str):
        return None
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()
    return text or None


def _trailer(video: dict, poster) -> dict | None:
    """A video entry of Steam (`mp4`) or RAWG (`data`): the small file when there is one, else the big one. Steam's
    answer now only lists streams (DASH, HLS) that a <video> cannot play outside Safari, but the mp4 of the same movie is
    still served at a path built from its id, so that is used when the answer has no mp4."""
    files = video.get("mp4") or video.get("data") or {}
    url = media_url(files.get("480") or files.get("max"))
    if not url and isinstance(video.get("id"), int) and video.get("hls_h264"):
        url = STEAM_MOVIE.format(movie_id=video["id"])
    return {"url": url, "poster": media_url(poster)} if url else None


def parse_steam(details) -> dict:
    """The parts of Steam's store page the app uses (it can be None or empty)."""
    out = {"description": None, "trailer": None, "screenshots": [], "metacritic": None}
    data = details if isinstance(details, dict) else {}
    out["description"] = clean_text(data.get("short_description"))
    movies = [m for m in data.get("movies") or [] if isinstance(m, dict)]
    for movie in sorted(movies, key=lambda m: not m.get("highlight")):  # the one Steam highlights first
        out["trailer"] = _trailer(movie, movie.get("thumbnail"))
        if out["trailer"]:
            break
    for shot in data.get("screenshots") or []:
        full = media_url(shot.get("path_full")) if isinstance(shot, dict) else None
        if full:
            out["screenshots"].append({"thumb": media_url(shot.get("path_thumbnail")) or full, "full": full})
    out["screenshots"] = out["screenshots"][:MAX_SCREENSHOTS]
    metacritic = data.get("metacritic")
    score = metacritic.get("score") if isinstance(metacritic, dict) else None
    out["metacritic"] = score if isinstance(score, int) and score > 0 else None
    return out


def names(items) -> list[str]:
    """The `name` of each entry of a RAWG list (publishers, platforms), RAWG's own order, without repeats or blanks."""
    found = []
    for item in items or []:
        name = item.get("name") if isinstance(item, dict) else None
        if isinstance(name, str) and name.strip() and name.strip() not in found:
            found.append(name.strip())
    return found


def parse_rawg(detail, movies, screenshots) -> dict:
    """The parts of RAWG's game page, trailers and screenshots the app uses (RAWG sends explicit nulls for some fields)."""
    out = {"description": None, "trailer": None, "screenshots": [], "metacritic": None, "esrb": None, "publishers": [], "platforms": []}
    data = detail if isinstance(detail, dict) else {}
    out["description"] = clean_text(data.get("description_raw"))
    out["publishers"] = names(data.get("publishers"))
    out["platforms"] = names([entry.get("platform") for entry in data.get("platforms") or [] if isinstance(entry, dict)])[:MAX_PLATFORMS]
    score = data.get("metacritic")
    out["metacritic"] = score if isinstance(score, int) and score > 0 else None
    esrb = data.get("esrb_rating")
    out["esrb"] = esrb.get("name") if isinstance(esrb, dict) and esrb.get("name") else None
    for movie in (movies or {}).get("results") or []:
        out["trailer"] = _trailer(movie, movie.get("preview")) if isinstance(movie, dict) else None
        if out["trailer"]:
            break
    for shot in (screenshots or {}).get("results") or []:
        image = media_url(shot.get("image")) if isinstance(shot, dict) else None
        if image:
            out["screenshots"].append({"thumb": image, "full": image})
    out["screenshots"] = out["screenshots"][:MAX_SCREENSHOTS]
    return out


def merge(steam: dict, rawg: dict) -> dict:
    """Steam first for the pictures and the description (it is in Spanish and curated), RAWG for the rest; whatever one
    lacks the other fills in (the description, then, is RAWG's English one: `description_lang` says which)."""
    return {
        "description": steam["description"] or rawg["description"],
        "description_lang": "es" if steam["description"] else "en",
        "trailer": steam["trailer"] or rawg["trailer"],
        "screenshots": steam["screenshots"] or rawg["screenshots"],
        "metacritic": rawg["metacritic"] or steam["metacritic"],
        "esrb": rawg["esrb"],
        "publishers": rawg["publishers"],
        "platforms": rawg["platforms"],
    }


async def _get_json(url: str, params: dict) -> dict | None:
    """The JSON answer, or None when the service fails (logged, never raised)."""
    try:
        resp = await my_utils._http_get(url, params, timeout=8)
        if not resp.ok:
            logger.warning(f"Outside game data error {resp.status_code} from {urlparse(url).netloc}: {redact_rawg_key(resp.content)}")
            return None
        body = resp.json()
        return body if isinstance(body, dict) else None
    except Exception as e:
        logger.warning(f"Error fetching outside game data from {urlparse(url).netloc}: {redact_rawg_key(e)}")
        return None


async def extras_of(rawg_id: int | None, steam_id: str | None) -> dict | None:
    """The extras of a game, or None when nobody could be asked (no ids, no key) or nobody answered: the caller shows no
    card then. An answer with nothing in it is a dict with empty fields."""
    steam_id = steam_id if steam_id and steam_id.isdigit() else None
    rawg_id = rawg_id if rawg_id and config.RAWG_API_KEY else None
    if not steam_id and not rawg_id:
        return None
    return await cache.get((rawg_id, steam_id), lambda: _fetch(rawg_id, steam_id))


async def _fetch(rawg_id: int | None, steam_id: str | None) -> dict | None:
    rawg_params = {"key": config.RAWG_API_KEY}
    game_url = RAWG_GAME.format(rawg_id=rawg_id) if rawg_id else None
    # no coroutine for what cannot be asked: None stands for "not asked", {} would stand for an answer
    rawg_detail, linked = await asyncio.gather(
        _get_json(game_url, rawg_params) if rawg_id else _none(),
        # a game created without its Steam id (by hand, or before Steam's link was kept) may still have it in RAWG's stores
        my_utils._steam_id_from_rawg_stores(rawg_id, rawg_params) if rawg_id and not steam_id else _none(),
    )
    steam_id = steam_id or linked or None
    steam_details = await _get_json(STEAM_DETAILS, {"appids": steam_id, "l": "spanish"}) if steam_id else None
    steam = parse_steam(((steam_details or {}).get(steam_id) or {}).get("data") if steam_id else None)
    # RAWG's videos and pictures only when Steam had none: they are a fallback, and each is a call
    movies, shots = await asyncio.gather(
        _get_json(game_url + "/movies", rawg_params) if rawg_id and not steam["trailer"] else _none(),
        _get_json(game_url + "/screenshots", rawg_params) if rawg_id and not steam["screenshots"] else _none(),
    )
    if steam_details is None and rawg_detail is None:
        return None  # nobody answered
    extras = merge(steam, parse_rawg(rawg_detail, movies, shots))
    # a service that was asked and did not answer leaves its part out: ask again soon, not tomorrow
    failed = [
        bool(steam_id) and steam_details is None,
        bool(rawg_id) and rawg_detail is None,
        bool(rawg_id) and not steam["trailer"] and movies is None,
        bool(rawg_id) and not steam["screenshots"] and shots is None,
    ]
    return Partial(extras) if any(failed) else extras


async def _none():
    return None


def clear() -> None:
    """Forget everything (the tests, and anybody who changes the key)."""
    cache.clear()
