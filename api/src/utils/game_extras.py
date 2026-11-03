"""What the world outside says about a game (a trailer, screenshots, a description, the critics' score, the age rating,
the publisher and the platforms it came out on), asked to IGDB, Steam and RAWG when a game's page opens and kept in memory
for a day (see outside_cache.py: nothing is stored in the database).

IGDB comes first for everything a game with an `igdb_id` has there; Steam (the game's `steam_id`) next, and RAWG (a
`rawg_id`) only for what is still missing, so a game that IGDB describes fully costs no RAWG request. The description is the
exception to the order: Steam's is in Spanish and curated, so it leads; without it IGDB's, then RAWG's, in English. It is all
optional: when nobody answers the page simply has no card. Prices are left out on purpose: they depend on the store, and a
game is played on several platforms."""
import asyncio
import html
import re
from urllib.parse import urlparse

from ..clients import igdb
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
MEDIA_HOSTS = ("steamstatic.com", "akamaihd.net", "rawg.io", "igdb.com")  # where the videos and pictures may come from

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


def parse_igdb(media) -> dict:
    """The parts of IGDB's page of a game the app uses (`igdb.media_of`; it can be None). Its trailer is a YouTube id."""
    data = media if isinstance(media, dict) else {}
    shots = [s for s in data.get("screenshots") or [] if media_url(s.get("full"))]
    trailer = data.get("trailer")
    return {
        "igdb_url": data.get("url"),
        "description": clean_text(data.get("description")),
        "trailer": {"url": None, "youtube": trailer, "poster": media_url(shots[0]["full"]) if shots else None} if trailer else None,
        "screenshots": [{"thumb": media_url(s["thumb"]) or media_url(s["full"]), "full": media_url(s["full"])} for s in shots],
        "metacritic": data.get("critic"),
        "esrb": data.get("esrb"),
        "publishers": list(data.get("publishers") or []),
        "platforms": list(data.get("platforms") or []),
    }


def merge(steam: dict, rawg: dict, igdb_data: dict | None = None) -> dict:
    """IGDB first for everything it has, then Steam, then RAWG; except the description: Steam's, in Spanish and curated, leads
    . The score is the critics' (`critic_source`: IGDB's own average, or Metacritic's
    when it comes from Steam or RAWG)."""
    igdb_data = igdb_data or parse_igdb(None)
    description = steam["description"] or igdb_data["description"] or rawg["description"]
    critic = igdb_data["metacritic"] or rawg["metacritic"] or steam["metacritic"]
    return {
        "description": description,
        "trailer": igdb_data["trailer"] or steam["trailer"] or rawg["trailer"],
        "screenshots": igdb_data["screenshots"] or steam["screenshots"] or rawg["screenshots"],
        "metacritic": critic,
        "critic_source": "igdb" if igdb_data["metacritic"] else "metacritic" if critic else None,
        "esrb": igdb_data["esrb"] or rawg["esrb"],
        "publishers": igdb_data["publishers"] or rawg["publishers"],
        "platforms": igdb_data["platforms"] or rawg["platforms"],
        "igdb_url": igdb_data["igdb_url"],
    }


async def _get_json(url: str, params: dict) -> dict | None:
    """The JSON answer, or None when the service fails (logged, never raised)."""
    rawg = urlparse(url).hostname == "api.rawg.io"
    try:
        resp = await (my_utils.rawg_get if rawg else my_utils._http_get)(url, params, timeout=8)
        if not resp.ok:
            logger.warning(f"Outside game data error {resp.status_code} from {urlparse(url).netloc}: {redact_rawg_key(resp.content)}")
            return None
        body = resp.json()
        return body if isinstance(body, dict) else None
    except my_utils.RawgPaused:
        return None  # RAWG failed a moment ago: it is not asked again yet, and said so then
    except Exception as e:
        logger.warning(f"Error fetching outside game data from {urlparse(url).netloc}: {redact_rawg_key(e)}")
        return None


async def extras_of(rawg_id: int | None, steam_id: str | None, igdb_id: int | None = None) -> dict | None:
    """The extras of a game, or None when nobody could be asked (no ids, no key) or nobody answered: the caller shows no
    card then. An answer with nothing in it is a dict with empty fields."""
    steam_id = steam_id if steam_id and steam_id.isdigit() else None
    rawg_id = rawg_id if rawg_id and config.RAWG_API_KEY else None
    igdb_id = igdb_id if igdb_id and igdb.configured() else None
    if not steam_id and not rawg_id and not igdb_id:
        return None
    return await cache.get((igdb_id, rawg_id, steam_id), lambda: _fetch(rawg_id, steam_id, igdb_id))


def _missing(igdb_data: dict, steam: dict) -> set[str]:
    """What neither IGDB nor Steam gave and RAWG could (the age rating alone is not worth a request)."""
    found = {
        "description": igdb_data["description"] or steam["description"],
        "trailer": igdb_data["trailer"] or steam["trailer"],
        "screenshots": igdb_data["screenshots"] or steam["screenshots"],
        "metacritic": igdb_data["metacritic"] or steam["metacritic"],
        "publishers": igdb_data["publishers"],
        "platforms": igdb_data["platforms"],
    }
    return {field for field, value in found.items() if not value}


async def _igdb_media(igdb_id: int) -> dict | None:
    """IGDB's page of the game, or None when it fails (logged, never raised) or has no such game."""
    try:
        return await asyncio.to_thread(igdb.media_of, igdb_id)
    except Exception as e:
        logger.warning(f"Error fetching IGDB media for game {igdb_id}: {e}")
        return None


async def _fetch(rawg_id: int | None, steam_id: str | None, igdb_id: int | None = None) -> dict | None:
    igdb_media = await _igdb_media(igdb_id) if igdb_id else None
    igdb_data = parse_igdb(igdb_media)
    rawg_params = {"key": config.RAWG_API_KEY}
    game_url = RAWG_GAME.format(rawg_id=rawg_id) if rawg_id else None
    # a game created without its Steam id (by hand, or before Steam's link was kept) may still have it in RAWG's stores; a game
    # IGDB answered for has it already, and RAWG is not asked just for that
    linked = await my_utils._steam_id_from_rawg_stores(rawg_id, rawg_params) if rawg_id and not steam_id and igdb_media is None else None
    steam_id = steam_id or linked or None
    steam_details = await _get_json(STEAM_DETAILS, {"appids": steam_id, "l": "spanish"}) if steam_id else None
    steam = parse_steam(((steam_details or {}).get(steam_id) or {}).get("data") if steam_id else None)
    # RAWG only for what IGDB and Steam did not give: it is a fallback, and each of its answers is a call
    missing = _missing(igdb_data, steam)
    ask_rawg = bool(rawg_id) and bool(missing)
    rawg_detail, movies, shots = None, None, None
    if ask_rawg:
        rawg_detail, movies, shots = await asyncio.gather(
            _get_json(game_url, rawg_params),
            _get_json(game_url + "/movies", rawg_params) if "trailer" in missing else _none(),
            _get_json(game_url + "/screenshots", rawg_params) if "screenshots" in missing else _none(),
        )
    asked = [bool(igdb_id), bool(steam_id), ask_rawg]
    answered = [igdb_media is not None, steam_details is not None, rawg_detail is not None]
    if any(asked) and not any(a for a, ok in zip(asked, answered) if ok):
        return None  # nobody answered
    extras = merge(steam, parse_rawg(rawg_detail, movies, shots), igdb_data)
    # a service that was asked and did not answer leaves its part out: ask again soon, not tomorrow
    failed = [
        bool(igdb_id) and igdb_media is None,
        bool(steam_id) and steam_details is None,
        ask_rawg and rawg_detail is None,
        ask_rawg and "trailer" in missing and movies is None,
        ask_rawg and "screenshots" in missing and shots is None,
    ]
    return Partial(extras) if any(failed) else extras


async def _none():
    return None


def clear() -> None:
    """Forget everything (the tests, and anybody who changes the key)."""
    cache.clear()
