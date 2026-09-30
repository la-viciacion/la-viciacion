# AGENTS.md

Entry point for any LLM/agent working on this repo. Read this first; the rest lives in `docs/`.

## What this is

**La Viciación**: a private app for a group of friends to track the time they spend playing video games (timers, manual sessions, per-season library, rankings, streaks, achievements) with Telegram notifications. Version 2.0 (Clockify was removed for good; no Clockify code, columns or webhooks remain, and none must be reintroduced; everything is stored in our own DB).

Four services, one `docker-compose.yml`:

| Service | Dir | Stack | Role |
|---|---|---|---|
| `laviciacion-api` | `api/` | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, MariaDB | Source of truth: REST API, business logic, in-process scheduler |
| `laviciacion-front` | `front/` | Vanilla JS (ES modules), no framework, no build step, nginx | PWA; nginx also proxies `/api` to the API |
| `laviciacion-bot` | `bot/` | Python 3.11, python-telegram-bot | Telegram bot, read-only except `/activate`; talks to the API as superadmin |
| `laviciacion-db` | `db/` | MariaDB | Data in `db/data/` (gitignored) |

## Documentation map

- [docs/architecture.md](docs/architecture.md): how the system works, data model, domain rules, auth, scheduler.
- [docs/development.md](docs/development.md): local setup, commands, tests, debugging.
- [docs/conventions.md](docs/conventions.md): code conventions, best practices, step-by-step recipes for common changes.
- [docs/migrations.md](docs/migrations.md): **Alembic rules, conventions and verification checklist (mandatory for any schema change).**
- [docs/deployment.md](docs/deployment.md): deployment stack, migrations, operations, rollback.
- [docs/roadmap.md](docs/roadmap.md): pending decisions (branching, versioning, CI) and known debt.
- [README.md](README.md): user/operator-facing documentation (config, seasons, notifications, manual sessions, deployment).

## Rules that must never be broken

1. **Migrations are the most delicate part of the project; read [docs/migrations.md](docs/migrations.md) before touching anything Alembic-related.** Schema changes go through an Alembic migration (`api/alembic/versions/`), never `create_all` or manual DB edits. Applied migrations are immutable (fix forward), history stays linear with a single head, revision ids are `NNN_name` of at most 32 chars, migrations are idempotent and refuse to run on inconsistent data instead of rewriting it, and no agent applies a migration to real data (`db/data/`, production) without explicit user approval.
2. **Do not store what can be derived.** Totals, rankings, streaks and the time of a library entry are computed from `game_timers` when requested; never add a table or column that caches them. **`season` is never written.** It is a generated column derived from the row's date. To move a row to another season, change its date. The running season comes only from `api/src/utils/seasons.py`.
3. **Authorization lives in the API** (`api/tests/test_endpoint_security.py` enforces it: the public endpoints are a fixed list; do not add one without updating it on purpose), never only in the front. Every route needs `get_current_active_user`; admin routes use `require_admin`; per-user data uses `ensure_self_or_admin`.
4. **The bot is read-only, with one deliberate exception: `/activate`**, which sets the sender's own `telegram_id` (via `PATCH /manage/users/{id}`, only from the app's group, never overwriting an existing id). Any other write is a design decision. It must only call generic endpoints; no other write logic, no direct DB access.
5. **Never commit secrets or data**: `.env`, DB dumps, `db/data/`, `db/init/*` (except `.gitkeep`) are gitignored. Only `.env.template` is tracked. Add new env vars to `.env.template` (with a placeholder) and to `api/src/config.py` / `bot/src/utils/config.py`.
6. **Front output is escaped by construction**: build markup with the `html` tagged template (`front/js/lib/html.js`), never assign strings to `innerHTML`.
7. **Telegram settings are runtime data** (table `app_settings`, edited from the admin panel), not `.env`. `.env` only seeds them once.
8. Do not add a build step, framework or bundler to the front without an explicit decision.

## Quick commands

```bash
# Stack
docker compose up -d --build
docker compose logs -f laviciacion-api

# API tests (from api/, needs the root .env or equivalent env vars)
cd api && python -m unittest discover -s tests -t .   # includes migration-history guards (needs alembic installed)

# Front tests + lint (from front/)
cd front && npm test && npm run lint
```

Full details in [docs/development.md](docs/development.md).

## Working agreements

- **Language**: code, identifiers, comments, commit messages and docs in English. The **UI and API user-facing error messages are in Spanish** (`api/src/utils/messages.py`, front strings); keep that.
- **Database storage / MariaDB:** on Windows/Docker Desktop set `DB_DATA=laviciacion_db_data` in `.env` (a named volume); the default `./db/data` bind mount breaks table-rebuilding migrations on MariaDB 12+. Never change the MariaDB major version of a database that has data by editing the image. Details: [docs/deployment.md](docs/deployment.md#database-storage-linux-vs-windows).
- Match the surrounding code style; comments explain *why*, not *what*. No dead code, no commented-out blocks.
- Keep changes focused; do not refactor unrelated code in the same change.
- Before finishing a change: run the API and front tests, lint the front, and if you touched behaviour described in `README.md` or `docs/`, update those docs in the same change.
- Add or update tests for any pure/business logic you touch (see existing examples in `api/tests/` and `front/tests/`).
- Ask before anything destructive or hard to reverse (dropping data, touching applied migrations, running migrations against real data, force-pushing).
- **Git workflow (branches, versioning, releases) is intentionally undefined until 2.0.0 ships**; see [docs/roadmap.md](docs/roadmap.md). Until then: work on the current branch, small commits in Conventional Commits style (`feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`), and do not create tags or releases.
