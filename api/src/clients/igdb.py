"""IGDB, the game database behind Twitch, as the backup of RAWG's search. It authenticates with the Twitch application
of TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET (client credentials): the token lasts about two months and is kept in memory
only. The secret travels in the body of the token request, never in a URL, so a failed request cannot quote it in the log."""
import datetime
import re
import threading
import time

import requests

from ..config import Config

config = Config()

TIMEOUT_SECONDS = 10
SEARCH_TIMEOUT_SECONDS = 5  # the picker searches while the player types: it cannot wait ten for a service that is down
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
IMAGE_URL = "https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg"
TOKEN_MARGIN_SECONDS = 3600  # renewed an hour before it expires
# What a player has played: main games, remakes, remasters, expanded games and ports. DLCs, expansions, standalone expansions
# and bundles (a trilogy, a legendary edition) are played too and the catalogue has them as games, so they are offered, but
# after the games proper. Packs, skins and updates (13, 14...) are not.
MAIN_TYPES = (0, 8, 9, 10, 11)
EXTRA_TYPES = (1, 2, 3, 4)
GAME_TYPES = "(" + ",".join(str(t) for t in MAIN_TYPES + EXTRA_TYPES) + ")"
FETCH_LIMIT = 25  # IGDB cannot sort a search: a wider net is cast and the best known of it is kept
FIELDS = (
    "name,slug,first_release_date,game_type,cover.image_id,genres.name,platforms.name,total_rating_count,"
    "involved_companies.developer,involved_companies.company.name"
)

# What IGDB says of a game besides its genres, kept in games.themes / keywords / franchises / collections
EXTRA_FIELDS = "themes.name,keywords.name,franchises.name,collections.name"
EXTRA_COLUMNS = ("themes", "keywords", "franchises", "collections")

_token_lock = threading.Lock()
_token: tuple[str, float] | None = None  # (token, when it expires)


class IgdbError(Exception):
    """IGDB did not answer or answered something unusable; the text is safe to log."""


class IgdbRefused(IgdbError):
    """Twitch refused the credentials: asking again will not help."""


def configured() -> bool:
    return bool(config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET)


def _access_token(renew: bool = False) -> str:
    global _token
    with _token_lock:
        if _token and not renew and _token[1] > time.time():
            return _token[0]
        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "client_id": config.TWITCH_CLIENT_ID,
                    "client_secret": config.TWITCH_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise IgdbError(f"Twitch did not answer ({type(e).__name__})") from None
        if not response.ok:
            error = IgdbRefused if response.status_code in (400, 401, 403) else IgdbError
            raise error(f"Twitch refused the credentials ({response.status_code})")
        body = response.json()
        _token = (body["access_token"], time.time() + body["expires_in"] - TOKEN_MARGIN_SECONDS)
        return _token[0]


def _quote(text: str) -> str:
    """The text as an Apicalypse string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _post(body: str, retried: bool = False, timeout: int = TIMEOUT_SECONDS) -> list[dict]:
    headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {_access_token(renew=retried)}"}
    try:
        response = requests.post(GAMES_URL, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise IgdbError(f"IGDB did not answer ({type(e).__name__})") from None
    if response.status_code == 401 and not retried:  # the token was revoked before it expired
        return _post(body, retried=True, timeout=timeout)
    if not response.ok:
        raise IgdbError(f"IGDB answered {response.status_code}")
    return response.json()


_ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


def _plain(name: str) -> str:
    """A name to compare: lower case, without punctuation and with roman numerals as digits ("Alan Wake II" is "Alan Wake 2")."""
    words = re.sub(r"[^\w ]", "", name.casefold()).split()
    return "".join(_ROMAN.get(word, word) for word in words)


def _same_name(a: str, b: str) -> bool:
    return _plain(a) == _plain(b)


def search_games(query: str, limit: int = 10) -> list[dict]:
    """The games IGDB finds for `query`, as the candidates of the game picker (`rawg_id` is None: they are not RAWG's)."""
    return [_candidate(item) for item in search_items(query, limit, timeout=SEARCH_TIMEOUT_SECONDS)]


def search_items(query: str, limit: int = 10, extras: bool = False, timeout: int = TIMEOUT_SECONDS) -> list[dict]:
    """The games IGDB finds for `query`, as IGDB gives them, best first.
    The ones named like the query come first, then the games proper, then the best known (most rated).

    It is asked while the player types, so a name that is half written has to match: IGDB's own search only knows whole
    words ("hollow kni" finds nothing), so the names that contain the text are asked for first, most rated first. Only when
    none does (the words are not together, "zelda tears") is the search, which tolerates that, asked.

    `extras` also asks for the themes, keywords, franchises and collections (`extras_of`): only the link of the catalogue
    needs them, the picker's list would carry kilobytes of keywords for nothing."""
    where = f"game_type = {GAME_TYPES} & version_parent = null"
    fields = f"{FIELDS},{EXTRA_FIELDS}" if extras else FIELDS
    found = _post(f"fields {fields}; where name ~ *{_quote(query)}* & {where}; sort total_rating_count desc; limit {FETCH_LIMIT};", timeout=timeout)
    if not found:
        found = _post(f"search {_quote(query)}; fields {fields}; where {where}; limit {FETCH_LIMIT};", timeout=timeout)
    found = [item for item in found if item.get("id") and item.get("name")]
    found.sort(key=lambda item: (
        not _same_name(item["name"], query), item.get("game_type") not in MAIN_TYPES, -(item.get("total_rating_count") or 0),
    ))
    return found[:limit]


def find_by_steam(steam_id: str) -> list[dict]:
    """The IGDB entries that have this Steam app (a game and, often, its editions or bundles), as IGDB gives them, with
    what `extras_of` reads."""
    return _post(
        f"fields name,first_release_date,game_type,version_parent,platforms.name,{EXTRA_FIELDS}; "
        f"where external_games.external_game_source = {STEAM_SOURCE} & external_games.uid = {_quote(str(steam_id))}; limit 10;"
    )


def clean_name(name: str) -> str:
    """A name of IGDB as it is kept in a comma separated column: an explanation in parentheses that has commas goes away
    ("4X (explore, expand, exploit, and exterminate)" is "4X") and any other comma becomes a space."""
    name = re.sub(r"\s*\([^)]*,[^)]*\)", "", name)
    return " ".join(name.replace(",", " ").split())


def _names(items) -> str:
    seen: dict[str, str] = {}
    for item in items or []:
        name = clean_name(item.get("name") or "")
        if name:
            seen.setdefault(name.casefold(), name)
    return ",".join(seen.values())


def extras_of(item: dict) -> dict[str, str]:
    """The themes, keywords, franchises and collections of an IGDB entry, each as the text for its column (empty when
    IGDB has none: the game is not asked about them again)."""
    return {column: _names(item.get(column)) for column in EXTRA_COLUMNS}


SCREENSHOT_THUMB = "https://images.igdb.com/igdb/image/upload/t_screenshot_med/{image_id}.jpg"
SCREENSHOT_FULL = "https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg"
MAX_SCREENSHOTS = 8
MAX_PLATFORMS = 10
ESRB_NAMES = {"E": "Everyone", "E10+": "Everyone 10+", "T": "Teen", "M": "Mature", "AO": "Adults Only", "RP": "Rating Pending"}
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{6,20}$")  # a YouTube id: it goes into the address of an embedded player


def media_of(igdb_id: int) -> dict | None:
    """What IGDB says that the page of a game shows: the summary (English), the trailer (a YouTube id), the screenshots, the
    critics' score, the ESRB age rating (as RAWG names it), the publishers and the platforms. None when IGDB has no such game."""
    found = _post(
        "fields summary,aggregated_rating,aggregated_rating_count,videos.video_id,videos.name,screenshots.image_id,"
        "age_ratings.rating_category.rating,age_ratings.rating_category.organization.name,"
        f"involved_companies.publisher,involved_companies.company.name,platforms.name; where id = {int(igdb_id)};"
    )
    if not found:
        return None
    item = found[0]
    videos = [v for v in item.get("videos") or [] if VIDEO_ID.match(str(v.get("video_id") or ""))]
    trailers = [v for v in videos if "trailer" in (v.get("name") or "").casefold()]  # the first trailer, else the first video
    shots = [s["image_id"] for s in item.get("screenshots") or [] if s.get("image_id")][:MAX_SCREENSHOTS]
    score = item.get("aggregated_rating")
    esrb = next(
        (
            ESRB_NAMES.get(str((a.get("rating_category") or {}).get("rating")))
            for a in item.get("age_ratings") or []
            if ((a.get("rating_category") or {}).get("organization") or {}).get("name") == "ESRB"
        ),
        None,
    )
    return {
        "description": (item.get("summary") or "").strip() or None,
        "trailer": (trailers or videos)[0]["video_id"] if (trailers or videos) else None,
        "screenshots": [{"thumb": SCREENSHOT_THUMB.format(image_id=i), "full": SCREENSHOT_FULL.format(image_id=i)} for i in shots],
        "critic": round(score) if isinstance(score, (int, float)) and score > 0 and item.get("aggregated_rating_count") else None,
        "esrb": esrb,
        "publishers": _names_of(
            c.get("company") for c in item.get("involved_companies") or [] if c.get("publisher")
        ),
        "platforms": _names_of(item.get("platforms"))[:MAX_PLATFORMS],
    }


def _names_of(items) -> list[str]:
    found: list[str] = []
    for item in items or []:
        name = (item or {}).get("name")
        if isinstance(name, str) and name.strip() and name.strip() not in found:
            found.append(name.strip())
    return found


def game_extras(igdb_id: int) -> dict[str, str] | None:
    """`extras_of` for the game with this IGDB id, or None when IGDB has no such game."""
    found = _post(f"fields {EXTRA_FIELDS}; where id = {int(igdb_id)};")
    return extras_of(found[0]) if found else None


STEAM_SOURCE = 1  # `external_game_source` of Steam in IGDB
DLC_TYPES = (1, 2, 4)  # dlc_addon, expansion, standalone_expansion


def game_details(igdb_id: int) -> dict | None:
    """What IGDB knows of a game, to create it: the same keys as RAWG's details minus the tags (None when IGDB has no
    such game) and its themes, keywords, franchises and collections. The tags are RAWG's vocabulary and IGDB's keywords are
    not the same: a game made from IGDB has no `tags`, it has those four columns instead."""
    found = _post(
        "fields name,slug,first_release_date,game_type,parent_game,cover.image_id,genres.name,involved_companies.developer,"
        f"involved_companies.company.name,external_games.external_game_source,external_games.uid,{EXTRA_FIELDS}; "
        f"where id = {int(igdb_id)};"
    )
    if not found:
        return None
    item, candidate = found[0], _candidate(found[0])
    steam = next(
        (e["uid"] for e in item.get("external_games") or [] if e.get("external_game_source") == STEAM_SOURCE and e.get("uid")),
        "",
    )
    released = item.get("first_release_date")
    return {
        "igdb_id": igdb_id,
        "name": candidate["name"],
        "slug": candidate["slug"],
        "dev": candidate["dev"],
        "release_date": datetime.datetime.fromtimestamp(released, datetime.timezone.utc).date() if released else None,
        "steam_id": steam,
        "image_url": candidate["image_url"],
        "genres": ",".join(candidate["genres"]),
        "is_dlc": item.get("game_type") in DLC_TYPES,
        "parent_igdb_id": item.get("parent_game") if item.get("game_type") in DLC_TYPES else None,
        **extras_of(item),
    }


def _candidate(item: dict) -> dict:
    released = item.get("first_release_date")
    image_id = (item.get("cover") or {}).get("image_id")
    developers = [
        name
        for company in item.get("involved_companies") or []
        if company.get("developer") and (name := (company.get("company") or {}).get("name"))
    ]
    return {
        "rawg_id": None,
        "igdb_id": item["id"],
        "source": "igdb",
        "name": item["name"],
        "slug": item.get("slug") or "",
        "released": datetime.datetime.fromtimestamp(released, datetime.timezone.utc).date().isoformat() if released else None,
        "image_url": IMAGE_URL.format(image_id=image_id) if image_id else None,
        "genres": [g["name"] for g in item.get("genres") or [] if g.get("name")],
        "platforms": [p["name"] for p in item.get("platforms") or [] if p.get("name")],
        "dev": ", ".join(developers) or None,
    }


def _day(stamp: int | None) -> datetime.date | None:
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).date() if stamp else None


def series_of(igdb_id: int) -> list[dict] | None:
    """The other games of the series (IGDB's collections) a game belongs to, as the saga of the game page takes them
    (empty when it has none), or None when IGDB has no such game. DLCs, packs and bundles of the series are left out."""
    found = _post(
        "fields collections.games.name,collections.games.slug,collections.games.first_release_date,"
        f"collections.games.game_type,collections.games.cover.image_id; where id = {int(igdb_id)};"
    )
    if not found:
        return None
    series: dict[int, dict] = {}
    for collection in found[0].get("collections") or []:
        for game in collection.get("games") or []:
            if game.get("id") == igdb_id or not game.get("name") or game.get("game_type") not in MAIN_TYPES:
                continue
            image_id = (game.get("cover") or {}).get("image_id")
            series.setdefault(game["id"], {
                "igdb_id": game["id"], "rawg_id": None, "name": game["name"], "slug": game.get("slug") or None,
                "image_url": IMAGE_URL.format(image_id=image_id) if image_id else None,
                "released": _day(game.get("first_release_date")).isoformat() if game.get("first_release_date") else None,
            })
    return list(series.values())


def release_dates(igdb_ids: list[int]) -> dict[int, datetime.date]:
    """The release day of each game IGDB has an **exact** date for (the earliest of its releases). A game announced for
    "2026" or "Q4" has a placeholder day in IGDB that is not a day it comes out: it is not in the answer."""
    ids = ",".join(str(int(i)) for i in igdb_ids)
    if not ids:
        return {}
    found = _post(f"fields release_dates.date,release_dates.date_format; where id = ({ids}); limit {len(igdb_ids)};")
    dates = {}
    for item in found:
        exact = [r["date"] for r in item.get("release_dates") or [] if r.get("date") and r.get("date_format") == 0]
        if exact:
            dates[item["id"]] = _day(min(exact))
    return dates


def parent_of(igdb_id: int) -> tuple[int, str] | None:
    """(IGDB id, name) of the base game when `igdb_id` is a DLC or an expansion of another one, else None."""
    found = _post(f"fields parent_game.name,game_type; where id = {int(igdb_id)};")
    parent = found[0].get("parent_game") if found and found[0].get("game_type") in DLC_TYPES else None
    return (parent["id"], parent.get("name") or "") if isinstance(parent, dict) and parent.get("id") else None
