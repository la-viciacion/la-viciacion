"""Hetzner Cloud's API: the state of the server the app runs on, its load over time and its traffic.

It takes a project token (HETZNER_API_TOKEN); a read-only one is enough. The API has no billing endpoint (invoices are
only in the console) and cannot see inside the machine, so there is no memory or disk usage: utils/server_status.py
estimates the cost from the prices the server carries."""
import datetime

import requests

URL = "https://api.hetzner.cloud/v1"
TIMEOUT_SECONDS = 15
METRIC_TYPES = "cpu,disk,network"


class HetznerError(Exception):
    """Hetzner refused or did not answer; the text is safe to show (it never holds the token)."""


def _message(response: requests.Response) -> str:
    try:
        text = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        text = response.reason or ""
    return str(text)[:200]


def _get(token: str, path: str, params: dict | None = None) -> dict:
    try:
        response = requests.get(f"{URL}{path}", params=params, headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise HetznerError(f"Hetzner no responde ({type(e).__name__})") from None
    if response.status_code in (401, 403):
        raise HetznerError(f"Hetzner rechaza el token ({_message(response)})")
    if response.status_code == 404:
        raise HetznerError("Hetzner no encuentra el servidor: revisa HETZNER_SERVER_ID")
    if not response.ok:
        raise HetznerError(f"Hetzner respondió {response.status_code}: {_message(response)}")
    try:
        return response.json()
    except ValueError:
        raise HetznerError("Hetzner devolvió una respuesta que no se entiende") from None


def server(token: str, server_id: str) -> dict:
    """The server with its type, prices and traffic of the billing month. Without `server_id`, the only one of the project."""
    if server_id:
        return _get(token, f"/servers/{server_id}")["server"]
    servers = _get(token, "/servers", {"per_page": 2})["servers"]
    if len(servers) != 1:
        raise HetznerError("El proyecto de Hetzner no tiene exactamente un servidor: indica cuál con HETZNER_SERVER_ID")
    return servers[0]


def metrics(token: str, server_id: int, start: datetime.datetime, end: datetime.datetime, step: int) -> dict:
    """The time series (`name -> {"values": [[unix seconds, "value"], ...]}`) between two instants, one point per `step` seconds."""
    params = {"type": METRIC_TYPES, "start": start.isoformat(), "end": end.isoformat(), "step": step}
    return _get(token, f"/servers/{server_id}/metrics", params)["metrics"]["time_series"]
