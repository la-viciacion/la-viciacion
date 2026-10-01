# Architecture

## Overview

```
Browser (PWA) ──► nginx (front, :3000) ──/api/──► FastAPI (api, :5000) ──► MariaDB (db)
                                                     ▲   │
Telegram bot (bot) ── HTTP, superadmin token ────────┘   └─► Telegram (notifications), RAWG, Gemini/OpenAI, SMTP, Sentry
```

- The **API is the only component that touches the DB** and holds all business rules.
- The **front** is a static SPA served by nginx; nginx proxies `/api/` to `API_UPSTREAM` (default `laviciacion-api:5000`; `front/nginx.conf.template`, rendered at container start), so the browser only talks to one origin.
- The **bot** is a read-only client (its one write is `/activate`, below): it logs in as the superadmin `admin` (password `GOD_ADMIN_PASS`) and uses generic endpoints (`/manage/...`, `/statistics/...`). It re-logs in on 401 and restarts itself when Telegram settings change in the API.
- The API sends notifications to Telegram itself (through `utils/my_utils.py`, using the token stored in `app_settings`); the bot handles interactive commands.
- All services share one `.env` (`env_file`); nothing secret or environment-specific is baked into images (they are built by CI, see [deployment](deployment.md#images)).

## API (`api/src/`)

```
main.py            app assembly: Sentry, god user + settings + achievements + VAPID seed,
                   routers, VersionedFastAPI (prefix /api/v1), CORS, request-timing middleware, scheduler start
config.py          Config: reads env vars (fails loudly if one is missing); falls back to root .env
auth.py            bcrypt, JWT (HS256), get_db, get_current_user/_active_user, require_admin,
                   ensure_self_or_admin
database/          database.py (engine, SessionLocal, Base), models.py (tables), schemas.py (Pydantic)
routers/           HTTP layer only: validation, auth, calling crud/utils, mapping errors to HTTP
crud/              DB access and queries (users, games, time_entries, rankings, achievements, ...)
utils/             domain logic and integrations (see below)
clients/google_ai.py, open_ai.py  one function per AI provider, each with the provider's official SDK (`google-genai`, `openai`); utils/ai.py picks one from the settings
```

Routers: `basic` (login, token, `/auth/active_user`, keepalive), `users` (profile (`?season=<year>|all`; `seasons.ALL` is the "every season" sentinel the stat queries accept), library (optionally `?game_id=` for the entries of one game), recommendations, avatar, password), `games`, `timers` (start/stop/manual/edit/history), `statistics`, `manage` (**admin panel API**: `/manage/overview` and `/manage/attention` for the panel's home (forgotten timers, players without Telegram ID, games without RAWG: computed on request), users, games, platforms (`/manage/platforms`: list with usage, create, rename, delete when unused), timers, library, achievements and awarded achievements (`/manage/user-achievements`: list, change date, revoke), RAWG sync, settings; router-level `require_admin`), `utils` (platforms, achievement images).

Utils worth knowing: `seasons.py` (single source of the season concept), `actions.py` (achievement checks, ranking/streak announcements, weekly resume), `streaks.py` (pure streak maths), `rate_limit.py`, `password_reset.py` + `email.py` (password recovery), `images.py`, `scheduler.py`, `settings.py` (runtime settings), `achievements.py`, `rawg_sync.py`, `messages.py` (Spanish user-facing error strings), `custom_exceptions.py`, `logger.py`.

### Layering rule

`router → crud / utils → models`. Routers do not build SQL; crud does not raise HTTP semantics beyond what it already does today; business rules that span entities go in `utils/` (or `crud/` when they are pure data operations). Put user-facing error text in `utils/messages.py`.

### Sync vs async

The DB layer is synchronous SQLAlchemy (do not introduce async DB drivers), so the rule is about where blocking code runs:

- **Routes are plain `def`.** FastAPI runs them in a worker thread (40 by default) and the connection pool covers them (`database.py`: 30 + 30 overflow). Anything that blocks (queries, bcrypt at login, image decoding for avatars) is fine there and nowhere else: a login or an avatar upload on the event loop froze every other request (measured: a `GET /keepalive` took 372 ms, up to 2 s, while six logins ran).
- **`async def` only when the route awaits the network** (RAWG search, creating a game, Telegram/push from the admin panel). Their database work goes through `run_in_threadpool`. `tests/test_async_discipline.py` fails any router `async def` that never awaits, and pins the list of allowed ones.
- **Slow follow-ups never run in the request.** Announcements, achievements, the effects of completing a game (HLTB, the AI, Telegram) are `BackgroundTasks` entrypoints in `utils/actions.py` (`after_timer_start`, `after_session_change`, `after_completion`): plain `def`s that open their own DB session and run their own event loop, serialized by `_check_lock`. The scheduler is a thread that does the same.
- Notification helpers (`utils/my_utils.py`, `utils/push.py`) are async, never raise, and offload blocking clients (`asyncio.to_thread`).

## Data model (`database/models.py`)

Tables: `users`, `games`, `users_games` (the per-user **library entry**, unique per user/game/platform/season), `game_timers` (sessions: running timers and finished/manual ones), `achievements`, `users_achievements` (once per user and season), `platform_tags` (platform catalogue; its ids are what `platform` columns store), `user_settings` (personal preferences, see below), `password_resets` (one-time recovery links, hashed), `app_settings`, `job_runs`.

Notes:
- **Foreign keys** (migration 016): `game_timers`, `users_games` and `users_achievements` point at `users`, `games`, `platform_tags` and `achievements`; `push_subscriptions.user_id` cascades and `app_settings.updated_by` is set to NULL when the user goes. The rest is RESTRICT: a user or game that still has sessions, library entries or achievements cannot be deleted, which is why `routers/manage.py` removes them first (after asking for confirmation). New tables that reference another one must declare their key in the model and in a migration.
- `game_timers` is the only sessions table (time entries were merged into it in migration 004). `is_active` = running timer; `duration_seconds` is set on stop.
- Nothing from Clockify remains in the schema (migration 010 dropped `users.clockify_*` and the `request_sync`, `logs` and `other_tags` tables); migrations 001-009 keep referring to it only to import old v1 backups.
- Login identifiers: `email` (unique, lower-case) and `username` (unique nickname, no `@`, no spaces); `telegram_id` is unique when set.
- `users.avatar` and `achievements.image` are stored as blobs.

## Domain rules

- **Seasons** = calendar years. `season` columns are `Computed` (generated, virtual) from the row date: `users_games.started_date`, `game_timers.start_time`, `users_achievements.date`. The current season is the server date's year (`TZ` must be set).
- **One game at a time per user**: at most one running timer; a new timer never starts before the user's last session ended; manual sessions must not overlap any other session (running timer included).
- **Manual sessions** (`POST /timers/manual`, `PATCH|DELETE /timers/{id}`): end after start, not in the future, ≤ 24 h, current season only for regular users (admins may edit closed seasons), game cannot be changed on an existing session. Manual changes check achievements silently (no group announcements).
- **Recommendations** are derived too (`games.recommendation_candidates` ranks every game that other active players (never the emergency account) have in their library and the user has never had in any season: by how many players share it, then how many completed it, then by name; `games.recommendations_for`, behind `GET /users/{username}/recommendations`, picks `limit` of them (default 12) by weighted random sampling without repeats, so each call can differ, and returns them in that ranked order. The weight (`recommendation_weight`, constants `W_*` in `crud/games.py`) is `1 + 2·players + 3·completions + 1.5·ln(1 + hours) + ln(1 + sessions)`, where hours and sessions are the finished sessions of the other active players on that game in any season, times up to 2 for the share of the user's own playing time in the game's genres (`genre_affinity`). Each candidate also carries `played_seconds` and `sessions`. Used by the **Recomendados** tab of the profile and the bot's **Recomendados** button, which asks for ten). The group notice of a completed game also suggests one of them (`games.recommended_games`, same genres as the game just completed): rewritten by the AI when it is configured (`NEW_GAME_RECOMMENDATION` prompt), as a plain line when it is not.
- **Derived data is never stored.** Totals, rankings, played days and streaks are computed from the sessions (`game_timers`) whenever they are requested (`crud/rankings.py`, `crud/time_entries.py`, `utils/streaks.py`); the time of a library entry is the sum of its sessions. There are no statistics tables to keep in sync, and a new season simply starts empty. Only what cannot be derived is stored: unlocked achievements (`users_achievements`), completions and scores.
- **Achievement texts belong to the database**: `Achievements.populate_achievements` runs once per API start and only creates the achievements the table lacks; it never rewrites an existing row, so what an admin edits (title, message) is kept. Changing a text in `utils/achievements.py` only affects achievements that do not exist yet.
- **Achievements are event-driven**: `actions.check_users` runs when a timer stops or an admin asks for it (**Comprobar logros**), and daily at 05:00 from the scheduler.
- **Ranking announcements compare before and after**: the stop-timer endpoint takes `actions.ranking_snapshot` before stopping and the background task (`after_session_change`) announces how the players and games rankings moved. No last-announced position is remembered; manual sessions and edits are silent.
- **A lost streak** (more than 10 days) is announced by the 05:00 check on the one day the last played day is two days ago (`streaks.lost_streak`).
- **Completion** of a game is only allowed for the current season, once per season, date not in the future.

## Auth

- Users log in with email or username + password (`POST /token`, OAuth2 password form); JWT valid `ACCESS_TOKEN_EXPIRE_MINUTES`, not renewed. The front stores it and sends `Authorization: Bearer`; a 401 clears the session.
- `admin` user ("Dios") is re-created/restored on every API start with `GOD_ADMIN_PASS`. It is a door, not a player: every query that aggregates or lists players (rankings, statistics by game or platform, `users.get_users` and so the achievement checks, weekly summaries and notices, push recipients) adds `models.not_god()`, and only the admin panel's user list shows it. Add that condition to any new query of that kind. There is no public sign-up: admins create accounts (it existed with an invitation key and was removed; add it back if it is ever needed).
- The only endpoints reachable without a token are `GET /`, `GET /keepalive`, `POST /token` (the only login), `POST /auth/forgot-password`, `POST /auth/reset-password` (password recovery, below) and `GET /utils/achievement-image/{key}` (loaded by `<img>`). `tests/test_endpoint_security.py` fixes that list and fails on any other open route, on any `/manage` route that is not admin-only and on any per-user route that never checks the owner. A new public endpoint is a security decision: add it to the test's `PUBLIC` set on purpose and document it here.
- **Web Push** (`utils/push.py`, `routers/push.py`, table `push_subscriptions`): a second channel, on by default (`push.enabled`); `push.ensure_vapid_keys` creates the server's single VAPID pair on the first start (and again, dropping all devices, if the stored private key cannot be read). Devices are only subscribed by their users, who are invited once after login (`front/js/ui/push-invite.js`). `my_utils.send_message` (group notices) calls `push.notify_group` and `send_message_to_user(..., user_id=)` calls `push.notify_user`; both never raise, so Telegram is unaffected. Delivery is blocking (`pywebpush`) and runs in a thread; devices answering 404/410 are deleted. Admins write notices in **Notificaciones → Redactar aviso**, which sends through one channel at a time: the app (`POST /manage/push/announce`, validated by `push.build_announcement`: plain text, title ≤ 80, message ≤ 240, link only a path or `#/` route of the app, image https, payload < 3.5 KB) or Telegram only (`POST /manage/telegram/announce`, `my_utils.send_announcement_to_chat`: to the admin's own chat, a user's `telegram_id` or the group; the text is escaped, so it cannot break the Markdown). `GET /manage/push/audience` tells the composer what each channel can reach. The private VAPID key is stored encrypted in `app_settings` and can only be created through `POST /manage/settings/push-keys`.
- **Running-timer notification**: when a timer starts, `actions.after_timer_start` pushes a pinned (`requireInteraction`), silent notification (title = game, body = elapsed time) to all of the user's devices; the scheduler job `timer_notices` re-sends it every 10 minutes (skipping timers younger than a minute, announced a moment ago) with the same tag, so each one replaces the last (the push TTL is 10 minutes: a late refresh is worse than none). Tapping it, or its **Parar** button (payload `button`), just opens the app, where the timer is stopped: the button deliberately does not stop anything by itself (an earlier version stopped it from the notification with a signed token and a confirmation step; it was dropped as more trouble than it was worth). The browser dismisses a notification when it or its button is tapped, so for `pinned` ones `notificationclick` opens the app and shows the same notification again under the same tag (with the text it had: it is refreshed by the next 10-minute push). iOS piles notifications up instead of replacing them by tag, so for `quiet` payloads the service worker closes the notifications with the same tag (`getNotifications({tag})`) right before showing the new one. Action buttons do not exist on iOS. When the timer stops (`POST /timers/stop`, or an admin in `/manage/timers`), `actions.after_timer_stop` replaces it with an unpinned "Timer parado · 1h 25min". `silent` and `renotify` cannot be combined (Chrome throws), so quiet payloads (`quiet: true`) never renotify. Android may delay the refreshes while the phone is idle; iOS ignores `requireInteraction`, so there it is refreshed but not pinned. The elapsed-time text is `push.elapsed_text`.
- **Password recovery** (`routers/basic.py`, `utils/password_reset.py`, `utils/email.py`, table `password_resets`, migration 017). `POST /auth/forgot-password {login}` (username or email) always answers the same 202, whether the account exists or not, and emails a link to the address stored on the account; `503` only when mail is not configured (`SMTP_HOST`, `SMTP_EMAIL` and `PUBLIC_URL`, see `.env.template`). The link is `PUBLIC_URL/#/reset-password?token=...` (fragment: never sent to a server or logged); the token is 256 random bits, only its SHA-256 is stored, it lasts 1 hour, works once, and asking again cancels the previous link. `POST /manage/settings/test-email` (admin) sends a diagnostic email to the asking admin's address, and `GET /manage/settings` reports the mail status without the password. `POST /auth/reset-password {token, new_password}` checks the password rules first (a weak one does not burn the link), claims the token and changes the hash in one transaction, which also signs out every session (`pwv`). Disabled accounts and accounts without an email get nothing. Throttled in memory: 3 links per account and hour, 20 requests per client and hour, 20 wrong links per client per 15 min (the per-client buckets only apply when the real client address is known, see below). The email is sent from a background task, so the response does not depend on it; a failure is only logged (never the token).
- Failed logins are throttled in memory (`utils/rate_limit.py`, HTTP 429). The per-account limit always applies; the per-client one only when the real client address is known (`client_key`: a private peer such as the nginx container is ignored, otherwise everybody would share one bucket and anyone could lock the rest out; set `FORWARDED_ALLOW_IPS` to make uvicorn trust the proxy in front). It is per process, another reason to run a single API replica.
- Tokens carry `pwv`, a keyed digest of the password hash (`auth.password_fingerprint`); `get_current_user` rejects tokens whose digest no longer matches, so a password change revokes older sessions.
- Uploaded images are validated by content (`utils/images.py`: real PNG/JPEG, size and pixel limits), never by the declared content type. 500 responses must not echo exception text: log it and return `messages.INTERNAL_ERROR`.
- Interactive docs are removed unless `API_DOCS_ENABLED=true` (see `main.py`).

## Scheduler (`utils/scheduler.py`)

Runs inside the API process (thread ticking every 30 s). Jobs: `weekly_summary`, `timer_notices` (every 10 minutes, only while push is ready: refreshes the pinned timer notification), `forgotten_timers` (hourly), `daily_streaks` (05:00: achievements check + lost streaks). There is no season-rollover job: rankings are computed per season on demand. Each run is recorded in `job_runs` (claimed atomically) so restarts never repeat a run, and a job due while the API was down still runs within a grace window. The due-time logic is pure functions (`weekly_slot`, `daily_slot`, `hourly_slot`, `timer_notice_slot`, `is_due`) covered by `api/tests/test_scheduler.py`. **Run only one API replica**: scaling out would need the claim/lock logic reviewed.

## Runtime settings (`utils/settings.py`)

Table `app_settings` (global, admin-edited); keys are validated/coerced by `settings.coerce`. The Telegram token is stored encrypted (key derived from `SECRET_KEY`; rotating `SECRET_KEY` requires re-entering it) and is never returned to the panel. `.env` values (`TELEGRAM_*`) only seed the table the first time.

## Personal settings (`utils/user_settings.py`)

Table `user_settings`: one row per user, one typed nullable column per preference; NULL (or no row) means "use the default", and the defaults live in code. Each new preference is an additive `ADD COLUMN ... NULL` migration. Edited by the user (or an admin) through `GET/PATCH /users/{username}/settings` from Profile → Ajustes; `null` resets one to its default. Today: `forgotten_timer_hours` (whole hours, 1-24, default 4), read by the hourly `forgotten_timers` job, so the reminder can arrive up to an hour after the chosen time.

## Front (`front/`)

No framework/build step. ES modules loaded by `index.html` → `js/main.js`.

```
js/main.js        hash router (#/, #/profile, #/admin), session handling, page lifecycle
js/lib/           api (fetch wrapper + session), html (escaping template tag), format, password, platforms, seasons
js/ui/            layout (navbar shell), modal, toast, icons
js/pages/         auth/ (login, recover), home/ (timer, history, completion, sessions, game-picker), profile/, admin/ (entities, form, dialogs, rawg-sync, settings)
css/              one stylesheet per area
assets/icons/     PWA icons (favicon, manifest, push notification icon and badge)
sw.js             service worker: caches nothing (keeps the app installable) and shows push notifications
```

Page module contract (documented at the top of `main.js`): exports `active`, optional `mainClass`, `adminOnly`, `render({ user, main, avatarUrl, isCurrent })`, optional `dispose()`. Always check `isCurrent()` after any `await` before touching the DOM. `adminOnly` is UX only; the API enforces it.

## Bot (`bot/src/`)

`app.py` wires handlers; `routes/` holds the conversation flows (`basic_routes`, `my_routes`, `ranking_routes`); `utils/config.py` is a singleton that logs in to the API, fetches Telegram settings (`GET /manage/settings/telegram`) and watches them every 60 s (exits to be restarted by Docker if they change); `utils/my_utils.py` wraps sending messages and API requests; `utils/messages.py` holds the texts.

**Access control** (`utils/access.py` + `MyUtils.gate`, a `TypeHandler` in group -1 that runs before every handler): an update is served only if the chat is private or the group configured in the app (`telegram.group_id`) **and** the sender's Telegram id is the `telegram_id` of an active account (looked up with `GET /users/`). Identity is never the Telegram `@username`. Other groups and channels get no answer at all; handlers read the account from `context.user_data["app_user"]`. `/start` (a welcome that points to `/activate`) and `/activate` are the only commands for people not linked yet, and they work only inside the app's group; `/activate`: it links the sender's Telegram id to the account whose app username equals their Telegram `@username` (case-insensitively; the account must be active and have no id yet, an existing id is never overwritten, so changing one needs an admin) through `PATCH /manage/users/{id}`; afterwards the `@username` no longer matters. It is listed in the command menu only for the group (`set_my_commands` with a chat scope); the gate is what enforces it.

## External services

RAWG (game metadata and covers, `RAWG_API_KEY`; the old `RAWG_URL` with `key=` in it still works), SMTP (`utils/email.py`, outgoing mail: only the password recovery link, optional), an AI provider (optional: Google Gemini or OpenAI; provider, key, model and on/off switch are `ai.*` settings edited from the admin panel, seeded once from `AI_*`/`OPENAI_*`; `utils/ai.py`). `utils/ai_prompts.py` is the registry of the places the AI writes (`USES`: id, label, default prompt): from it `settings.py` generates, for each, the setting `ai.prompt.<id>` (default: the code's prompt; `PUT /manage/settings` with `null` deletes the override) and the switch `ai.use.<id>`, and callers ask for a notice with `send_message(..., ai_use=<id>)`. Adding a place that uses the AI means adding an entry to `USES`; ids are stored, so they are never renamed, Sentry (optional, separate DSN per service), Telegram Bot API.
