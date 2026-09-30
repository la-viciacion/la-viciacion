# Architecture

## Overview

```
Browser (PWA) ──► nginx (front, :3000) ──/api/──► FastAPI (api, :5000) ──► MariaDB (db)
                                                     ▲   │
Telegram bot (bot) ── HTTP, superadmin token ────────┘   └─► Telegram (notifications), RAWG, OpenAI, SMTP, Sentry
```

- The **API is the only component that touches the DB** and holds all business rules.
- The **front** is a static SPA served by nginx; nginx proxies `/api/` to `laviciacion-api:5000` (`front/nginx.conf`), so the browser only talks to one origin.
- The **bot** is a read-only client: it logs in as the superadmin `admin` (password `GOD_ADMIN_PASS`) and uses generic endpoints (`/manage/...`, `/statistics/...`). It re-logs in on 401 and restarts itself when Telegram settings change in the API.
- The API sends notifications to Telegram itself (through `utils/my_utils.py`, using the token stored in `app_settings`); the bot handles interactive commands.
- All services share one `.env` (`env_file`); nothing secret is baked into images.

## API (`api/src/`)

```
main.py            app assembly: Sentry, create_all (safety net only), god user + settings seed,
                   routers, VersionedFastAPI (prefix /api/v1), CORS, request-timing middleware, scheduler start
config.py          Config: reads env vars (fails loudly if one is missing); falls back to root .env
auth.py            bcrypt, JWT (HS256), get_db, get_current_user/_active_user, require_admin,
                   ensure_self_or_admin
database/          database.py (engine, SessionLocal, Base), models.py (tables), schemas.py (Pydantic)
routers/           HTTP layer only: validation, auth, calling crud/utils, mapping errors to HTTP
crud/              DB access and queries (users, games, time_entries, rankings, achievements, ...)
utils/             domain logic and integrations (see below)
clients/open_ai.py OpenAI client wrapper
```

Routers: `basic` (login, token, `/auth/active_user`, keepalive), `users` (profile, library, avatar, password), `games`, `timers` (start/stop/manual/edit/history), `statistics`, `manage` (**admin panel API**: users, games, timers, library, achievements and awarded achievements (`/manage/user-achievements`: list, change date, revoke), RAWG sync, settings; router-level `require_admin`), `utils` (platforms, achievements, playing).

Utils worth knowing: `seasons.py` (single source of the season concept), `actions.py` (recompute stats/rankings/streaks, announcements, weekly resume), `scheduler.py`, `settings.py` (runtime settings), `achievements.py`, `rawg_sync.py`, `messages.py` (Spanish user-facing error strings), `custom_exceptions.py`, `logger.py`.

### Layering rule

`router → crud / utils → models`. Routers do not build SQL; crud does not raise HTTP semantics beyond what it already does today; business rules that span entities go in `utils/` (or `crud/` when they are pure data operations). Put user-facing error text in `utils/messages.py`.

### Sync vs async

Routes and helpers are a mix of `def` and `async def`; the DB layer is synchronous SQLAlchemy. Do not introduce async DB drivers. Long/background work uses `BackgroundTasks` (see `manage.py` recompute and RAWG sync) or the scheduler thread.

## Data model (`database/models.py`)

Tables: `users`, `users_statistics`, `games`, `games_statistics`, `users_games` (the per-user **library entry**, unique per user/game/platform/season), `game_timers` (sessions: running timers and finished/manual ones), `achievements`, `users_achievements` (once per user and season), `platform_tags` (platform catalogue; its ids are what `platform` columns store), `app_settings`, `job_runs`.

Notes:
- `game_timers` is the only sessions table (time entries were merged into it in migration 004). `is_active` = running timer; `duration_seconds` is set on stop.
- Nothing from Clockify remains in the schema (migration 010 dropped `users.clockify_*` and the `request_sync`, `logs` and `other_tags` tables); migrations 001-009 keep referring to it only to import old v1 backups.
- Login identifiers: `email` (unique, lower-case) and `username` (unique nickname, no `@`, no spaces); `telegram_id` is unique when set.
- `users.avatar` and `achievements.image` are stored as blobs.

## Domain rules

- **Seasons** = calendar years. `season` columns are `Computed` (generated, virtual) from the row date: `users_games.started_date`, `game_timers.start_time`, `users_achievements.date`. The current season is the server date's year (`TZ` must be set).
- **One game at a time per user**: at most one running timer; a new timer never starts before the user's last session ended; manual sessions must not overlap any other session (running timer included).
- **Manual sessions** (`POST /timers/manual`, `PATCH|DELETE /timers/{id}`): end after start, not in the future, ≤ 24 h, current season only for regular users (admins may edit closed seasons), game cannot be changed on an existing session. Manual changes recompute stats silently (no group announcements).
- **Stats, achievements and ranking announcements are event-driven**: they run when a timer stops or an admin edits data (`actions.recompute_*`), not on a schedule.
- **Completion** of a game is only allowed for the current season, once per season, date not in the future.

## Auth

- Users log in with email or username + password (`POST /token`, OAuth2 password form); JWT valid `ACCESS_TOKEN_EXPIRE_MINUTES`, not renewed. The front stores it and sends `Authorization: Bearer`; a 401 clears the session.
- `admin` user ("Dios") is re-created/restored on every API start with `GOD_ADMIN_PASS`. Public sign-up is parked; admins create accounts.
- The only endpoints reachable without a token are `GET /`, `GET /keepalive`, `POST /token` (the only login), `POST /signup` (invitation key) and `GET /utils/achievement-image/{key}` (loaded by `<img>`). `tests/test_endpoint_security.py` fixes that list and fails on any other open route, on any `/manage` route that is not admin-only and on any per-user route that never checks the owner. A new public endpoint is a security decision: add it to the test's `PUBLIC` set on purpose and document it here.
- Failed logins and wrong invitation keys are throttled in memory (`utils/rate_limit.py`, HTTP 429). It is per process, another reason to run a single API replica.
- Tokens carry `pwv`, a keyed digest of the password hash (`auth.password_fingerprint`); `get_current_user` rejects tokens whose digest no longer matches, so a password change revokes older sessions.
- Uploaded images are validated by content (`utils/images.py`: real PNG/JPEG, size and pixel limits), never by the declared content type. 500 responses must not echo exception text: log it and return `messages.INTERNAL_ERROR`.
- Interactive docs are removed unless `API_DOCS_ENABLED=true` (see `main.py`).

## Scheduler (`utils/scheduler.py`)

Runs inside the API process (thread ticking every 30 s). Jobs: `weekly_summary`, `forgotten_timers` (hourly), `daily_streaks` (05:00), `season_rollover`. Each run is recorded in `job_runs` (claimed atomically) so restarts never repeat a run, and a job due while the API was down still runs within a grace window. The due-time logic is pure functions (`weekly_slot`, `daily_slot`, `hourly_slot`, `is_due`) covered by `api/tests/test_scheduler.py`. **Run only one API replica**: scaling out would need the claim/lock logic reviewed.

## Runtime settings (`utils/settings.py`)

Table `app_settings`; keys are validated/coerced by `settings.coerce`. The Telegram token is stored encrypted (key derived from `SECRET_KEY`; rotating `SECRET_KEY` requires re-entering it) and is never returned to the panel. `.env` values (`TELEGRAM_*`) only seed the table the first time.

## Front (`front/`)

No framework/build step. ES modules loaded by `index.html` → `js/main.js`.

```
js/main.js        hash router (#/, #/profile, #/admin), session handling, page lifecycle
js/lib/           api (fetch wrapper + session), html (escaping template tag), format, password, platforms, seasons
js/ui/            layout (navbar shell), modal, toast, icons
js/pages/         login, home/ (timer, history, sessions, game-picker), profile/, admin/ (entities, form, dialogs, rawg-sync, settings)
css/              one stylesheet per area
sw.js             pass-through service worker (caches nothing; keeps the app installable)
```

Page module contract (documented at the top of `main.js`): exports `active`, optional `mainClass`, `adminOnly`, `render({ user, main, avatarUrl, isCurrent })`, optional `dispose()`. Always check `isCurrent()` after any `await` before touching the DOM. `adminOnly` is UX only; the API enforces it.

## Bot (`bot/src/`)

`app.py` wires handlers; `routes/` holds the conversation flows (`basic_routes`, `my_routes`, `ranking_routes`); `utils/config.py` is a singleton that logs in to the API, fetches Telegram settings (`GET /manage/settings/telegram`) and watches them every 60 s (exits to be restarted by Docker if they change); `utils/my_utils.py` wraps sending messages and API requests; `utils/messages.py` / `read_messages.py` hold texts.

## External services

RAWG (game metadata and covers, `RAWG_URL`), SMTP (`utils/email.py`, outgoing mail; no endpoint uses it yet), OpenAI (optional, `OPENAI_API_KEY`, prompts in `utils/ai_prompts.py`), Sentry (optional, separate DSN per service), Telegram Bot API.
