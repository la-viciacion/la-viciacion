"""Searching a city by name, with Open-Meteo's geocoding (free, no key).

The player types a city and picks one of the answers; what is stored is its name and the coordinates of its centre,
never a GPS fix. The achievements that depend on the weather are the only thing that uses them.
"""
import requests

from .logger import LogManager

logger = LogManager().get_logger()

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
TIMEOUT = 6
MIN_QUERY = 2
MAX_QUERY = 80
RESULTS = 8


class PlacesUnavailable(Exception):
    """The geocoder did not answer (or answered something unusable)."""


def label(item: dict) -> str:
    """"Madrid, Comunidad de Madrid, España": the name, the region and the country, without repeating one."""
    parts = []
    for key in ("name", "admin1", "country"):
        value = (item.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def parse(payload: dict) -> list[dict]:
    """The answers of the geocoder as {name, latitude, longitude}, leaving out the ones without coordinates."""
    found = []
    for item in payload.get("results") or []:
        latitude, longitude = item.get("latitude"), item.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)) or not label(item):
            continue
        found.append({"name": label(item)[:255], "latitude": round(float(latitude), 5), "longitude": round(float(longitude), 5)})
    return found


def search(query: str) -> list[dict]:
    """Cities that match `query`, best first. Raises PlacesUnavailable if the geocoder cannot be reached."""
    query = (query or "").strip()[:MAX_QUERY]
    if len(query) < MIN_QUERY:
        return []
    try:
        response = requests.get(
            GEOCODING_URL, params={"name": query, "count": RESULTS, "language": "es", "format": "json"}, timeout=TIMEOUT
        )
        if not response.ok:
            raise PlacesUnavailable(f"HTTP {response.status_code}")
        return parse(response.json())
    except (requests.RequestException, ValueError) as e:
        logger.warning("Open-Meteo geocoding failed: " + str(e))
        raise PlacesUnavailable(str(e))
