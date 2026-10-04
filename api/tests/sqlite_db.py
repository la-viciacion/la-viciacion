"""An in-memory SQLite database with the app's tables, for tests that need real queries.

SQLite has no YEAR(): it is registered so the generated `season` columns work.
"""
import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from src.database import models


def _year(value):
    return None if value is None else int(str(value)[:4])


def make_session(threads: bool = False):
    """`threads=True` for code that runs part of its work in a worker thread (FastAPI's threadpool): one
    connection shared by every thread, which is fine for a test that never runs two things at once."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool) if threads else create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def register(dbapi_connection, _):
        dbapi_connection.create_function("YEAR", 1, _year, deterministic=True)

    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()
