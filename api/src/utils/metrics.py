"""Prometheus metrics of the API: how many requests each route gets, how long it takes to answer and how many are in
flight, plus the process figures `prometheus_client` collects by itself (memory, CPU, open files, GC).

`GET /metrics` is served here, by the middleware, and not by a router: it is outside `/api` on purpose, because the front's
nginx only forwards `/api/`, so it is only reachable from inside the stack's network (Prometheus asks for it by container
name, see prometheus/prometheus.yml). It has no login for that reason; it holds counters and latencies, no user data."""
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

METRICS_PATH = "/metrics"
UNMATCHED = "unmatched"  # a path no route owns (a 404): one label, not one per scanned URL

REQUESTS = Counter("laviciacion_http_requests_total", "Requests answered", ["method", "route", "status"])
# the time to start answering: what the client waits for, not the background work that runs after the response
LATENCY = Histogram(
    "laviciacion_http_request_duration_seconds",
    "Seconds until the response starts",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
IN_FLIGHT = Gauge("laviciacion_http_requests_in_flight", "Requests being handled, background tasks included")


def route_label(scope) -> str:
    """The route's template (`/api/v1/timers/active/{user_id}`), never the real URL, so the labels stay a fixed set."""
    route = scope.get("route")
    return getattr(route, "path", None) or UNMATCHED


class MetricsMiddleware:
    """A plain ASGI middleware (like RequestLogMiddleware, for the same reason). It is the outermost one, so it sees every
    request, and it answers `/metrics` itself without counting it."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == METRICS_PATH and scope["method"] == "GET":
            return await self._expose(send)

        started = time.perf_counter()
        status = 500  # what a crash that never reached the response will be
        answered = False

        async def send_and_measure(message):
            nonlocal status, answered
            if message["type"] == "http.response.start":
                status = message["status"]
                answered = True
                LATENCY.labels(scope["method"], route_label(scope)).observe(time.perf_counter() - started)
            await send(message)

        IN_FLIGHT.inc()
        try:
            await self.app(scope, receive, send_and_measure)
        finally:
            IN_FLIGHT.dec()
            route = route_label(scope)
            if not answered:
                LATENCY.labels(scope["method"], route).observe(time.perf_counter() - started)
            REQUESTS.labels(scope["method"], route, str(status)).inc()

    @staticmethod
    async def _expose(send):
        body = generate_latest()
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", CONTENT_TYPE_LATEST.encode()), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
