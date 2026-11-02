"""IGDB, the game database behind Twitch, as the backup of RAWG's search. It authenticates with the Twitch application
of TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET (client credentials): the token lasts about two months and is kept in memory
only. The secret travels in the body of the token request, never in a URL, so a failed request cannot quote it in the log."""
import datetime
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


def search_games(query: str, limit: int = 10) -> list[dict]:
    """The games IGDB finds for `query`, as the candidates of the game picker (`rawg_id` is None: they are not RAWG's)."""
    found = _post(
        f"search {_quote(query)}; "
        "fields name,slug,first_release_date,cover.image_id,genres.name,platforms.name,"
        "involved_companies.developer,involved_companies.company.name; "
        f"limit {int(limit)};"
    )
    return [_candidate(item) for item in found if item.get("id") and item.get("name")]


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
        "source": "igdb",
        "name": item["name"],
        "slug": item.get("slug") or "",
        "released": datetime.datetime.fromtimestamp(released, datetime.timezone.utc).date().isoformat() if released else None,
        "image_url": IMAGE_URL.format(image_id=image_id) if image_id else None,
        "genres": [g["name"] for g in item.get("genres") or [] if g.get("name")],
        "platforms": [p["name"] for p in item.get("platforms") or [] if p.get("name")],
        "dev": ", ".join(developers) or None,
    }
