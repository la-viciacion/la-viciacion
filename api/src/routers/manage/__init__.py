"""Admin panel API: data management for users, games, sessions, library and
achievements. Every route requires an admin (router-level dependency).

There is one router, `router` (common.py), with the admin check and the audit log
wired once for all of it; each module of the package adds the routes of one area
to it, so importing them here is what registers them.

Deletes of records that other data hangs from are refused with a 409 that
lists what would be lost, unless `force=true` is passed - the panel shows that
list to the admin and re-sends with force after an explicit confirmation.
"""
from . import (
    overview,
    achievements,
    system,
    users,
    games,
    syncs,
    sessions,
    platforms,
    challenges,
    notices,
    ai_usage,
    polls,
)
from .common import router

# the modules of the areas, each of which registers its routes on `router` when imported
AREAS = (overview, achievements, system, users, games, syncs, sessions, platforms, challenges, notices, ai_usage, polls)

__all__ = ["AREAS", "router"]
