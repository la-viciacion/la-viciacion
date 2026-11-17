"""How the API is doing, for the admin panel: requests, how long they take to answer, errors, what is in flight and the
process's memory, over a window, plus the routes that are slowest and busiest.

Everything comes from the API's own metrics (utils/metrics.py) as the Prometheus of the monitoring profile stored them, so
nothing is kept here (rule 2); the answer is held in memory for a minute, like the server panel's. A window has data only from
the day the API began to be scraped, and a quantile is an estimate from the histogram's buckets (the figure is as exact as them)."""
import datetime

from ..clients import prometheus
from .server_status import WINDOWS
from .ttl_cache import TtlCache

CACHE_SECONDS = 60
MIN_ROUTE_REQUESTS = 3  # a route asked twice has no p95 worth telling
ROUTES_SHOWN = 10
MIN_RATE_SECONDS = 60  # a rate needs at least two scrapes (every 30 s) inside its window

# The keepalive is asked by the compose healthcheck every 30 s: it would top every table and tint every figure, so it is left out
REAL = 'route!~".*/keepalive"'
REQUESTS = f"laviciacion_http_requests_total{{{REAL}}}"
BUCKETS = f"laviciacion_http_request_duration_seconds_bucket{{{REAL}}}"
IN_FLIGHT = "laviciacion_http_requests_in_flight"
SERVER_ERRORS = f'laviciacion_http_requests_total{{{REAL},status=~"5.."}}'

_cache = TtlCache(CACHE_SECONDS)


def now_queries(seconds: int) -> dict[str, str]:
    """What the window as a whole says: the figures of the tiles."""
    window = f"{seconds}s"
    return {
        "requests": f"sum(increase({REQUESTS}[{window}]))",
        "errors": f"sum(increase({SERVER_ERRORS}[{window}]))",
        "p50": f"histogram_quantile(0.5, sum by (le) (increase({BUCKETS}[{window}])))",
        "p95": f"histogram_quantile(0.95, sum by (le) (increase({BUCKETS}[{window}])))",
        "in_flight": IN_FLIGHT,
        "memory": "process_resident_memory_bytes",
    }


def series_queries(step: int) -> dict[str, str]:
    """The expressions drawn over time; a rate is taken over as long as a point of the chart lasts, so a peak between two
    points is part of one of them instead of falling in the gap."""
    window = f"{max(step, MIN_RATE_SECONDS)}s"
    return {
        "requests": f"60 * sum(rate({REQUESTS}[{window}]))",
        "errors": f"60 * sum(rate({SERVER_ERRORS}[{window}]))",
        "p95": f"histogram_quantile(0.95, sum by (le) (rate({BUCKETS}[{window}])))",
        "memory": "process_resident_memory_bytes",
    }


def route_queries(seconds: int) -> dict[str, str]:
    window = f"{seconds}s"
    return {
        "count": f"sum by (method, route) (increase({REQUESTS}[{window}]))",
        "p95": f"histogram_quantile(0.95, sum by (method, route, le) (increase({BUCKETS}[{window}])))",
        "errors": f"sum by (method, route) (increase({SERVER_ERRORS}[{window}]))",
    }


def shape_routes(found: dict[str, list]) -> dict:
    """The slowest (by p95) and the busiest routes, from what Prometheus says of each (method, route)."""
    def by_route(rows):
        return {(labels.get("method", ""), labels.get("route", "")): value for labels, value in rows}

    count, p95, errors = by_route(found["count"]), by_route(found["p95"]), by_route(found["errors"])
    rows = [
        {"method": method, "route": route, "requests": round(total), "p95": p95.get((method, route)), "errors": round(errors.get((method, route), 0))}
        for (method, route), total in count.items()
        if round(total) >= MIN_ROUTE_REQUESTS
    ]
    slowest = sorted((r for r in rows if r["p95"] is not None), key=lambda r: -r["p95"])[:ROUTES_SHOWN]
    busiest = sorted(rows, key=lambda r: -r["requests"])[:ROUTES_SHOWN]
    return {"slowest": slowest, "busiest": busiest}


def shape_now(now: dict) -> dict:
    return {
        "requests": None if now["requests"] is None else round(now["requests"]),
        "errors": 0 if now["errors"] is None else round(now["errors"]),
        "p50": now["p50"],
        "p95": now["p95"],
        "in_flight": None if now["in_flight"] is None else round(now["in_flight"]),
        "memory": now["memory"],
    }


def _fetch(url: str, window: str, now: datetime.datetime) -> dict:
    seconds, step = WINDOWS[window]
    start = now - datetime.timedelta(seconds=seconds)
    current = {key: prometheus.instant(url, expression) for key, expression in now_queries(seconds).items()}
    charts = {key: prometheus.series(url, expression, start, now, step) for key, expression in series_queries(step).items()}
    routes = shape_routes({key: prometheus.vector(url, expression) for key, expression in route_queries(seconds).items()})
    return {"window": window, "now": shape_now(current), "charts": charts, "routes": routes, "has_data": current["requests"] is not None}


def overview(url: str, window: str, refresh: bool = False) -> dict:
    """The panel's data for one window (1h, 24h, 7d, 30d). `refresh` asks Prometheus again instead of reusing the last minute."""
    if refresh:
        _cache.clear()
    return _cache.get(window, lambda: _fetch(url, window, datetime.datetime.now(datetime.timezone.utc)))


def clear() -> None:
    _cache.clear()
