import logging
from contextlib import asynccontextmanager

import sentry_sdk

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import Config
from .database.database import SessionLocal
from .crud import users as users_crud
from .crud.achievements import Achievements
from .utils import push as push_utils
from .utils import scheduler, settings
from .routers import activity, basic, games, group, manage, push, statistics, timers, users, utils
from .utils.logger import LogManager
from .utils.request_log import RequestLogMiddleware

log_manager = LogManager()
logger = log_manager.get_logger()


config = Config()


if config.SENTRY_URL is not None and config.SENTRY_URL != "":
    sentry_sdk.init(
        dsn=config.SENTRY_URL,
        # a sample is enough for a small private app; errors are always reported
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=config.ENVIRONMENT,
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
API_PREFIX = "/api/v1"
excluded_paths = ["/keepalive"]
full_excluded_paths = [f"{API_PREFIX}{path}" for path in excluded_paths]
uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(EndpointFilter(excluded_paths))

with SessionLocal() as db:
    users_crud.ensure_god_user(db)
    settings.seed_from_env(db)
    push_utils.ensure_vapid_keys(db)  # the routers' `push` module has the same name
    Achievements().populate_achievements(db)

@asynccontextmanager
async def lifespan(_: FastAPI):
    scheduler.start()
    yield


# Swagger/ReDoc/openapi.json list every endpoint: only served when API_DOCS_ENABLED=true
docs = config.API_DOCS_ENABLED
app = FastAPI(
    title="LaViciacion API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=f"{API_PREFIX}/docs" if docs else None,
    redoc_url=f"{API_PREFIX}/redoc" if docs else None,
    openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
    swagger_ui_oauth2_redirect_url=f"{API_PREFIX}/docs/oauth2-redirect",
)

# A new incompatible version (/api/v2) is one more router with its own prefix, built the same way
api_v1 = APIRouter(prefix=API_PREFIX)
for router in (basic, users, games, statistics, timers, activity, group, manage, push, utils):
    api_v1.include_router(router.router)
app.include_router(api_v1)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.add_middleware(RequestLogMiddleware, excluded_paths=full_excluded_paths)
