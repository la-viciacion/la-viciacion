"""What the world outside says about a game (a trailer, screenshots, a short description in Spanish, Metacritic, the age
rating), asked to Steam and RAWG when a game's page opens and
kept in memory for a day.

Nothing is stored in the database: it is outside data that changes rarely, so each worker keeps the answers it got for
CACHE_SECONDS (and forgets them when it restarts). It is all optional: Steam knows only the games that have a `steam_id`
and RAWG the ones with a `rawg_id`, so a game from Nintendo gets only what RAWG has, and when neither answers the page
simply has no card. A failure is remembered for a few minutes so a page opened again and again does not ask every time.
Prices are left out on purpose: they depend on the store, and a game is played on several platforms."""
import asyncio
import html
import re
import time
from urllib.parse import urlparse

from ..config import Config
from . import my_utils
from .logger import LogManager
from .redaction import redact_rawg_key

logger = LogManager().get_logger()
config = Config()

CACHE_SECONDS = 24 * 3600
FAILURE_SECONDS = 5 * 60
MAX_CACHED = 500  # games kept; the one that expires first goes when there are more
MAX_SCREENSHOTS = 8
MEDIA_HOSTS = ("steamstatic.com", "akamaihd.net", "rawg.io")  # where the videos and pictures may come from

STEAM_MOVIE = "https://cdn.akamai.steamstatic.com/steam/apps/{movie_id}/movie480.mp4"  # what a plain <video> can play
STEAM_DETAILS = "https://store.steampowered.com/api/appdetails"
RAWG_GAME = "https://api.rawg.io/api/games/{rawg_id}"

_cache: dict[tuple, tuple[float, dict | None]] = {}  # (rawg id, steam id) -> (when it expires, the extras or None if nothing answered)
_asking: dict[tuple, asyncio.Task] = {}  # the answer being fetched, so a burst of requests asks once


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


def parse_rawg(detail, movies, screenshots) -> dict:
    """The parts of RAWG's game page, trailers and screenshots the app uses (RAWG sends explicit nulls for some fields)."""
    out = {"trailer": None, "screenshots": [], "metacritic": None, "esrb": None}
    data = detail if isinstance(detail, dict) else {}
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
    lacks the other fills in."""
    return {
        "description": steam["description"],
        "trailer": steam["trailer"] or rawg["trailer"],
        "screenshots": steam["screenshots"] or rawg["screenshots"],
        "metacritic": rawg["metacritic"] or steam["metacritic"],
        "esrb": rawg["esrb"],
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


def _remember(key: tuple, value: dict | None, seconds: float) -> None:
    if len(_cache) >= MAX_CACHED:
        del _cache[min(_cache, key=lambda k: _cache[k][0])]
    _cache[key] = (time.time() + seconds, value)


async def extras_of(rawg_id: int | None, steam_id: str | None) -> dict | None:
    """The extras of a game, or None when nobody could be asked (no ids, no key) or nobody answered: the caller shows no
    card then. An answer with nothing in it is a dict with empty fields."""
    steam_id = steam_id if steam_id and steam_id.isdigit() else None
    rawg_id = rawg_id if rawg_id and config.RAWG_API_KEY else None
    if not steam_id and not rawg_id:
        return None
    key = (rawg_id, steam_id)
    cached = _cache.get(key)
    if cached and cached[0] > time.time():
        return cached[1]
    if key not in _asking:
        _asking[key] = asyncio.create_task(_fetch_once(key))
    return await asyncio.shield(_asking[key])  # shielded: a caller that goes away does not cancel the others' answer


async def _fetch_once(key: tuple) -> dict | None:
    try:
        return await _fetch(*key)
    finally:
        del _asking[key]


async def _fetch(rawg_id: int | None, steam_id: str | None) -> dict | None:
    rawg_params = {"key": config.RAWG_API_KEY}
    # no coroutine for what cannot be asked: None stands for "not asked", {} would stand for an answer
    steam_details, rawg_detail = await asyncio.gather(
        _get_json(STEAM_DETAILS, {"appids": steam_id, "l": "spanish"}) if steam_id else _none(),
        _get_json(RAWG_GAME.format(rawg_id=rawg_id), rawg_params) if rawg_id else _none(),
    )
    steam = parse_steam(((steam_details or {}).get(steam_id) or {}).get("data") if steam_id else None)
    # RAWG's videos and pictures only when Steam had none: they are a fallback, and each is a call
    wants_trailer = rawg_id and not steam["trailer"]
    wants_shots = rawg_id and not steam["screenshots"]
    movies, shots = await asyncio.gather(
        _get_json(RAWG_GAME.format(rawg_id=rawg_id) + "/movies", rawg_params) if wants_trailer else _none(),
        _get_json(RAWG_GAME.format(rawg_id=rawg_id) + "/screenshots", rawg_params) if wants_shots else _none(),
    )
    rawg = parse_rawg(rawg_detail, movies, shots)
    extras = merge(steam, rawg)
    answered = any(answer is not None for answer in (steam_details, rawg_detail))
    if not answered:
        _remember((rawg_id, steam_id), None, FAILURE_SECONDS)
        return None
    _remember((rawg_id, steam_id), extras, CACHE_SECONDS)
    return extras


async def _none():
    return None


def clear() -> None:
    """Forget everything (the tests, and anybody who changes the key)."""
    _cache.clear()
