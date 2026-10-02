"""An in-memory SQLite database with the app's tables, for tests that need real queries.

SQLite has no YEAR(): it is registered so the generated `season` columns work.
"""
import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.database import models


def _year(value):
    return None if value is None else int(str(value)[:4])


def make_session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def register(dbapi_connection, _):
        dbapi_connection.create_function("YEAR", 1, _year, deterministic=True)

    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False)()
