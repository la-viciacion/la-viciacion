"""Prometheus' HTTP API, for the figures node-exporter reports about the machine that Hetzner cannot see (memory, disk
space, load). It is the Prometheus of the monitoring profile of docker-compose.yml, inside the stack's network: no token, and the
address comes from PROMETHEUS_URL."""
import datetime

import requests

TIMEOUT_SECONDS = 10


class PrometheusError(Exception):
    """Prometheus did not answer or answered something unusable; the text is safe to show."""


def _query(base: str, path: str, params: dict) -> list[dict]:
    try:
        response = requests.get(f"{base}/api/v1/{path}", params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise PrometheusError(f"Prometheus no responde ({type(e).__name__})") from None
    try:
        body = response.json()
    except ValueError:
        raise PrometheusError(f"Prometheus respondió {response.status_code} sin un cuerpo que se entienda") from None
    if not response.ok or body.get("status") != "success":
        raise PrometheusError(f"Prometheus rechaza la consulta ({str(body.get('error') or response.reason or response.status_code)[:200]})")
    return body["data"]["result"]


def instant(base: str, expression: str) -> float | None:
    """The value of an expression right now, or None when it has no data (node-exporter has not been scraped yet)."""
    result = _query(base, "query", {"query": expression})
    return float(result[0]["value"][1]) if result else None


def series(base: str, expression: str, start: datetime.datetime, end: datetime.datetime, step: int) -> list[list[float]]:
    """`[[unix seconds, value], ...]` of an expression between two instants, one point per `step` seconds."""
    result = _query(base, "query_range", {"query": expression, "start": start.timestamp(), "end": end.timestamp(), "step": step})
    return [[int(stamp), round(float(value), 3)] for stamp, value in (result[0]["values"] if result else [])]
