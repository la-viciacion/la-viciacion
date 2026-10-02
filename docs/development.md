# Development

## Prerequisites

- Docker + Docker Compose (the reference way to run everything)
- Python 3.14 (API and bot) and Node 20.19+ / 22.13+ (front, ESLint 10) if you run services outside Docker
- A `.env` at the repo root: `cp .env.template .env` and fill it in. API and bot fall back to this file when not in Docker (`find_dotenv`); real environment variables always win.

When running the API outside Docker, `MARIADB_HOST` must point to a reachable DB (e.g. `127.0.0.1` with the compose DB published on `127.0.0.1:3307`; adapt the port in the URL/host as needed) instead of the container name `laviciacion-db`.

## Run the stack

**On Windows set `DB_DATA=laviciacion_db_data` in your `.env`** (line commented in `.env.template`) before the first `up`: the database then lives in a Docker named volume. With the default `./db/data` bind mount, MariaDB 12+ cannot rebuild tables on Docker Desktop and migration 012 fails (`errno: 194 "Tablespace is missing for a table"`). Backups then go through `mariadb-dump`, not by copying `db/data`. See [deployment.md](deployment.md#database-storage-linux-vs-windows).


```bash
docker compose up -d --build           # everything, building the images from the Dockerfiles (production pulls the published ones instead)
docker compose up -d --build laviciacion-api   # rebuild one service
docker compose logs -f laviciacion-api
docker compose down                    # keeps db/data
```

**Development stack (`*-dev` names):** `docker-compose.dev.yml` is an override of the main file that builds from the checkout and names images and containers `laviciacion-<service>-dev` (the database keeps the `mariadb` image, container `laviciacion-db-dev`). Always use it together with the main file:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f laviciacion-api
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

It is an alternative to the main stack, not a second one next to it: same project, same service names (so `.env` hostnames such as `laviciacion-db` keep working), same ports (`FRONT_HOST_PORT`...) and the same database volume, so switching between the two recreates the containers and keeps the data. To avoid retyping the two files, set `COMPOSE_FILE=docker-compose.yml;docker-compose.dev.yml` in your shell (`:` instead of `;` on Linux/macOS); then plain `docker compose up -d --build` is the dev stack.

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

Run the API tests with the venv, not the global Python: `test_migrations.py` needs `alembic` and the other pinned dependencies. The bot has unit tests (`cd bot && python -m unittest discover -s tests -t .`, no API, no Telegram, no network): the access gate and `/activate`, the text of every statistic and ranking, that every keyboard button has a handler in the state where it is shown (and every handler a button), the API client (login, retry with a fresh token, the settings and the restart when they change) and the error handler. `tests/support.py` sets the environment the bot reads at import and gives fake Telegram updates. API tests cover pure logic (`scheduler`, `settings`, `my_utils`), the static integrity of the Alembic history, and queries against an in-memory SQLite database (`tests/sqlite_db.py`, which registers `YEAR()` for the generated `season` columns); anything MariaDB-specific still needs a real database. Tests whose file is named `test_mariadb_*.py` run on a **real MariaDB** and skip themselves without one. To run them locally start a throwaway server and point `TEST_MARIADB_URL` at it (each test class creates and drops its own `lavi_test_*` database; never use a server with real data):

```bash
docker run -d --name lavi-test-db -e MARIADB_ROOT_PASSWORD=testpw -p 127.0.0.1:3399:3306 mariadb:12.3.3
TEST_MARIADB_URL=mysql+pymysql://root:testpw@127.0.0.1:3399 venv/Scripts/python.exe -m unittest discover -s tests -t . -p "test_mariadb_*.py"
docker rm -f lavi-test-db
```

Use the version `docker-compose.yml` pins. The HTTP-level tests (`test_mariadb_api_*.py`) make real requests to the routers on a migrated database: `tests/api_support.py` mounts them as `main.py` does, points `get_db` at the test database (migrated once per run, emptied before each test), builds users, games and tokens the way the application does (`self.user("ana")`, `self.api("GET", "/users/ana", as_user="ana")`) and replaces what the application does after answering (`actions.after_*`, announcements) with recorders in `self.background`. RAWG and HowLongToBeat are faked in every test, and a test that reaches the network fails: the developer's `.env` (which `Config` reads) may hold a real RAWG key. A new route or business rule gets its test there, written as the request a client makes. The work the application does on its own (achievements and announcements, Telegram delivery, the scheduler, the RAWG sync, Web Push) is tested the same way in `test_mariadb_background_*.py`, `test_mariadb_scheduler.py`, `test_mariadb_rawg_sync.py` and `test_mariadb_push_delivery.py`: the real functions run against the database, Telegram is `FakeBot`, push and RAWG are recorders or fakes, and the clock is an argument (`scheduler.tick(now)`), so nothing waits and nothing leaves the process. The bot is tested against the real API in `test_mariadb_bot_contract.py`: its handlers run with their HTTP calls answered by the API under test, as the emergency administrator, so renaming a field the bot reads (`game_name`, `played_time`, `current_streak`...) fails there and not in the group chat. An `async def` test needs `unittest.IsolatedAsyncioTestCase` too: `ApiTestCase` fails an async test in a plain `TestCase`, which would otherwise pass without running. To see what a change leaves untested, run the suite under `coverage` (`coverage run --source=src -m unittest discover -s tests -t .` then `coverage report -m`; install it with `pip install coverage`, it is not a project dependency).

CI runs them on every PR against exactly that version (it reads the tag from the compose file) with `REQUIRE_MARIADB_TESTS=1`, so a missing server there fails instead of skipping, and weekly against `lts` and `latest` as an early warning. Front tests cover `js/lib` and `pages/home/sessions`. Prefer extracting pure functions so new logic can be tested the same way (see [roadmap](roadmap.md) for planned integration tests).

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
