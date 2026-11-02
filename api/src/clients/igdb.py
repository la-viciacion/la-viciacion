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

_token_lock = threading.Lock()
_token: tuple[str, float] | None = None  # (token, when it expires)


class IgdbError(Exception):
    """IGDB did not answer or answered something unusable; the text is safe to log."""


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
            raise IgdbError(f"Twitch refused the credentials ({response.status_code})")
        body = response.json()
        _token = (body["access_token"], time.time() + body["expires_in"] - TOKEN_MARGIN_SECONDS)
        return _token[0]


def _quote(text: str) -> str:
    """The text as an Apicalypse string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _post(body: str, retried: bool = False) -> list[dict]:
    headers = {"Client-ID": config.TWITCH_CLIENT_ID, "Authorization": f"Bearer {_access_token(renew=retried)}"}
    try:
        response = requests.post(GAMES_URL, data=body.encode("utf-8"), headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise IgdbError(f"IGDB did not answer ({type(e).__name__})") from None
    if response.status_code == 401 and not retried:  # the token was revoked before it expired
        return _post(body, retried=True)
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
    """The games IGDB finds for `query`, as the candidates of the game picker (`rawg_id` is None: they are not RAWG's).
    The ones named like the query come first, then the games proper, then the best known (most rated).

    It is asked while the player types, so a name that is half written has to match: IGDB's own search only knows whole
    words ("hollow kni" finds nothing), so the names that contain the text are asked for first, most rated first. Only when
    none does (the words are not together, "zelda tears") is the search, which tolerates that, asked."""
    where = f"game_type = {GAME_TYPES} & version_parent = null"
    found = _post(f"fields {FIELDS}; where name ~ *{_quote(query)}* & {where}; sort total_rating_count desc; limit {FETCH_LIMIT};")
    if not found:
        found = _post(f"search {_quote(query)}; fields {FIELDS}; where {where}; limit {FETCH_LIMIT};")
    found = [item for item in found if item.get("id") and item.get("name")]
    found.sort(key=lambda item: (
        not _same_name(item["name"], query), item.get("game_type") not in MAIN_TYPES, -(item.get("total_rating_count") or 0),
    ))
    return [_candidate(item) for item in found[:limit]]


STEAM_SOURCE = 1  # `external_game_source` of Steam in IGDB
DLC_TYPES = (1, 2, 4)  # dlc_addon, expansion, standalone_expansion


def game_details(igdb_id: int) -> dict | None:
    """What IGDB knows of a game, to create it: the same keys as RAWG's details minus the tags (None when IGDB has no
    such game). The tags are RAWG's vocabulary and IGDB's keywords are not the same: a game made from IGDB has none."""
    found = _post(
        "fields name,slug,first_release_date,game_type,cover.image_id,genres.name,involved_companies.developer,"
        "involved_companies.company.name,external_games.external_game_source,external_games.uid; "
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
