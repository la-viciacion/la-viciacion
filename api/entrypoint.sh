#!/bin/sh
set -e

# The db healthcheck (docker-compose) already gates container startup, but
# double-check the DB actually accepts connections before migrating —
# a fresh environment importing a large pre-migration backup via
# docker-entrypoint-initdb.d can still take a while after MariaDB itself
# reports healthy.
python -c "
import sys
import time

from src.database.database import engine
from sqlalchemy import text

for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        break
    except Exception as e:
        print(f'Waiting for database... ({attempt + 1}/30): {e}', flush=True)
        time.sleep(2)
else:
    print('Database not reachable after 60s, aborting.', file=sys.stderr)
    sys.exit(1)
"

alembic upgrade head
exec uvicorn src.main:app --log-level warning --proxy-headers --host 0.0.0.0 --port 5000
