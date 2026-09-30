# Development

## Prerequisites

- Docker + Docker Compose (the reference way to run everything)
- Python 3.13 (API) / 3.11 (bot) and Node 20+ (front) if you run services outside Docker
- A `.env` at the repo root: `cp .env.template .env` and fill it in. API and bot fall back to this file when not in Docker (`find_dotenv`); real environment variables always win.

When running the API outside Docker, `MARIADB_HOST` must point to a reachable DB (e.g. `127.0.0.1` with the compose DB published on `127.0.0.1:3307`; adapt the port in the URL/host as needed) instead of the container name `laviciacion-db`.

## Run the stack

**On Windows set `DB_DATA=laviciacion_db_data` in your `.env`** (line commented in `.env.template`) before the first `up`: the database then lives in a Docker named volume. With the default `./db/data` bind mount, MariaDB 12+ cannot rebuild tables on Docker Desktop and migration 012 fails (`errno: 194 "Tablespace is missing for a table"`). Backups then go through `mariadb-dump`, not by copying `db/data`. See [deployment.md](deployment.md#database-storage-linux-vs-windows).


```bash
docker compose up -d --build           # everything
docker compose up -d --build laviciacion-api   # rebuild one service
docker compose logs -f laviciacion-api
docker compose down                    # keeps db/data
```

- Front: http://localhost:3000 (API proxied at `/api/`)
- API: http://127.0.0.1:5000 (interactive docs at `/api/v1/docs` only with `API_DOCS_ENABLED=true` in `.env`)
- DB: `127.0.0.1:3307`
- The API container runs `alembic upgrade head` on every start (`api/entrypoint.sh`).
- Logs are written to `api/logs/` and `bot/logs/` (gitignored).

## Tests and lint

```bash
# API (unittest; from api/, needs env vars from the root .env)
cd api
python -m venv venv                        # once; venv/ is gitignored
venv/Scripts/python.exe -m pip install -r requirements.txt   # Linux/macOS: venv/bin/python
venv/Scripts/python.exe -m unittest discover -s tests -t .

# Front (from front/)
cd front
npm install
npm test          # node --test on tests/
npm run lint      # ESLint
npm run dev       # static server on :3000 (API must be reachable at /api)
```

Run the API tests with the venv, not the global Python: `test_migrations.py` needs `alembic` and the other pinned dependencies. The bot's access rules have unit tests (`cd bot && python -m unittest discover -s tests -t .`); the rest of the bot is untested. API tests cover pure logic (`scheduler`, `settings`, `my_utils`), the static integrity of the Alembic history, and queries against an in-memory SQLite database (`tests/sqlite_db.py`, which registers `YEAR()` for the generated `season` columns); anything MariaDB-specific still needs a real database. Front tests cover `js/lib` and `pages/home/sessions`. Prefer extracting pure functions so new logic can be tested the same way (see [roadmap](roadmap.md) for planned integration tests).

## Database and migrations

**Read [migrations.md](migrations.md) first; it is mandatory for any schema change.** Day to day:

```bash
cd api
alembic current
alembic upgrade head
alembic revision -m "short description" --rev-id 010_short_name   # then write it by hand
```

Run these inside the API container (`docker compose exec laviciacion-api alembic ...`) or locally with the env set, always against a throwaway database, never against real data. The `api/alembic/` folder shadows the `alembic` package when `api/` is on `sys.path`; `tests/test_migrations.py` works around it, keep it in mind for ad-hoc scripts.

To inspect data: connect any MySQL client to `127.0.0.1:3307` with `MARIADB_USER`/`MARIADB_PASSWORD`.

## Debugging tips

- `API_LOG_LEVEL=DEBUG` / `BOT_LOG_LEVEL=DEBUG` in `.env`, then recreate the container.
- Every request is logged with method, path, status and duration (except `/keepalive`).
- Sentry is disabled when `SENTRY_URL_API` / `SENTRY_URL_BOT` are empty.
- The scheduler ticks every 30 s; to test a job, call the pure slot functions or `scheduler.tick(now)` with a chosen `now` rather than waiting.
- Front changes are served with `Cache-Control: no-cache`, so a reload is enough; the service worker caches nothing.
- If `Environment variable 'X' not found` appears on start, add `X` to `.env` (and to `.env.template`).
