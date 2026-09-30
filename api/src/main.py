import datetime
import sentry_sdk
import logging

from sentry_sdk.types import Event, Hint
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi_versioning import VersionedFastAPI

from .config import Config
from .database import models
from .database.database import SessionLocal, engine
from .crud import users as users_crud
from .crud.achievements import Achievements
from .utils import push as push_utils
from .utils import scheduler, settings
from .routers import basic, games, manage, push, statistics, timers, users, utils
from .utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()


config = Config()


def before_send(event: Event, hint: Hint):
    # modify event here
    # logger.info("------BEFORE SENTRY------")
    # logger.info("Hint:")
    exc_info_str = str(hint.get("exc_info"))
    # logger.info(exc_info_str)
    return event


if config.SENTRY_URL is not None and config.SENTRY_URL != "":
    sentry_sdk.init(
        dsn=config.SENTRY_URL,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
        environment=config.ENVIRONMENT,
        before_send=before_send,
    )


class EndpointFilter(logging.Filter):
    """
    Filter to exclude specific endpoints from logging.
    """

    def __init__(self, excluded_paths: list):
        super().__init__()
        self.excluded_paths = excluded_paths

    def filter(self, record: logging.LogRecord) -> bool:
        return not any(path in record.getMessage() for path in self.excluded_paths)


# Exclude specific paths from logging configuration
base_path = "/api/v1"
excluded_paths = ["/keepalive"]
full_excluded_paths = [f"{base_path}{path}" for path in excluded_paths]
uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(EndpointFilter(excluded_paths))

models.Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    users_crud.ensure_god_user(db)
    settings.seed_from_env(db)
    push_utils.ensure_vapid_keys(db)  # the routers' `push` module has the same name
    Achievements().populate_achievements(db)

app = FastAPI(title="LaViciacion API", version="0.1.0")

app.include_router(basic.router)
app.include_router(users.router)
app.include_router(games.router)
app.include_router(statistics.router)
app.include_router(timers.router)
app.include_router(manage.router)
app.include_router(push.router)
app.include_router(utils.router)

app = VersionedFastAPI(app, version_format="{major}", prefix_format="/api/v{major}")

# Swagger/ReDoc/openapi.json list every endpoint: only served when API_DOCS_ENABLED=true
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect")


def remove_docs(application: FastAPI) -> None:
    application.router.routes[:] = [
        r
        for r in application.router.routes
        if not getattr(r, "path", "").endswith(DOCS_PATHS)
    ]
    for route in application.router.routes:
        if isinstance(getattr(route, "app", None), FastAPI):
            remove_docs(route.app)


if not config.API_DOCS_ENABLED:
    remove_docs(app)


@app.on_event("startup")
def start_scheduler():
    scheduler.start()


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_timestamp_to_logs(request, call_next):
    # Exclude logs from specific paths
    if request.url.path in full_excluded_paths:
        response = await call_next(request)
        return response
    else:
        start_time = datetime.datetime.now()
        response = await call_next(request)
        end_time = datetime.datetime.now()

        duration = end_time - start_time

        query_params = request.query_params

        if query_params:
            query_str = f"?{query_params}"
        else:
            query_str = ""

        logger.info(
            f'REQUEST - "{request.method} {request.url.path}{query_str}" - {response.status_code} - {duration}'
        )

        return response
