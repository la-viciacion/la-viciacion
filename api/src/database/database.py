from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config import Config

config = Config()

engine = create_engine(
    f"mysql+pymysql://{config.DB_USER}:{config.DB_PASS}@{config.DB_HOST}/{config.DB_NAME}",
    # a request thread holds a connection while it works: as many as the server has worker threads
    # (40 by default) plus the scheduler and the background checks, so nobody waits for one
    pool_size=30,
    max_overflow=30,
    # MariaDB drops connections idle for longer than its wait_timeout (8 h by default): check a
    # connection before using it and retire old ones, or the first request after a quiet night fails
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
