"""The routes the router modules declare, as the application publishes them under /api/v1.

Used by tests/test_mariadb_app_boot.py and tests/app_probe.py. It reads the router modules, not the
application, on purpose: how FastAPI stores mounted routes is an implementation detail that changes
between versions, while what a client can request is the contract.
"""
import re

from src.routers import basic, games, manage, push, statistics, timers, users, utils

BASE = "/api/v1"
ROUTERS = (basic, games, manage, push, statistics, timers, users, utils)


def declared_routes() -> list[tuple[str, str]]:
    """(method, published path), e.g. ("GET", "/api/v1/users/{username}")."""
    return sorted(
        {
            (method, f"{BASE}{route.path}")
            for module in ROUTERS
            for route in module.router.routes
            for method in route.methods
            if method not in ("HEAD", "OPTIONS")
        }
    )


def requestable(path: str) -> str:
    """The same path with every {parameter} filled in, to be requested."""
    return re.sub(r"\{[^}]+\}", "1", path)
