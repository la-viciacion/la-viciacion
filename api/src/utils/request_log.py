"""Request log line: method, path, status and duration of every request."""
import datetime
import time

from .logger import LogManager

logger = LogManager().get_logger()


class RequestLogMiddleware:
    """A plain ASGI middleware: `@app.middleware("http")` (BaseHTTPMiddleware) wraps every request
    in an extra task and copies the response stream, a cost paid on all requests for a log line."""

    def __init__(self, app, excluded_paths=()):
        self.app = app
        self.excluded_paths = set(excluded_paths)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in self.excluded_paths:
            return await self.app(scope, receive, send)
        started = time.perf_counter()
        status = 500  # what a crash that never reached the response will be

        async def send_and_note_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_note_status)
        finally:
            duration = datetime.timedelta(seconds=time.perf_counter() - started)
            query = scope.get("query_string", b"").decode("latin-1")
            logger.info(
                f'REQUEST - "{scope["method"]} {scope["path"]}{"?" + query if query else ""}" - {status} - {duration}'
            )
