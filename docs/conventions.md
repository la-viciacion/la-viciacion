# Conventions, best practices and recipes

## General

- Code, comments, commit messages and docs in **English**; UI text and user-facing API errors in **Spanish**.
- Comments say *why* (a non-obvious rule, a constraint, a trade-off), not what the code does. Docstrings at the top of a module are welcome when the module encodes a concept (see `seasons.py`, `scheduler.py`).
- Prefer small pure functions for logic so it is testable without DB, clocks or network.
- No dead code, no commented-out code, no TODOs without a home in [roadmap.md](roadmap.md).
- Handle errors at the boundaries (routers, integrations); do not swallow exceptions silently. Log with the module logger (`LogManager().get_logger()`), never `print`.
- Secrets never in code, logs, responses or commits. Never return password hashes, tokens or encrypted settings to clients.

## API (Python)

- Follow the layering `router → crud/utils → models`.
- Use Pydantic schemas (`database/schemas.py`) for request bodies and `response_model`; validate at the schema/route level, enforce invariants in the business layer too (the API is the last line of defence, the front's checks are UX).
- Endpoints must return JSON-friendly data: convert SQLAlchemy `Row`s to dicts (`row._mapping`, see `plain()` in `routers/statistics.py`); a `Row` in a response is a 500.
- Never return `str(e)` in a 500: log the error and answer with `messages.INTERNAL_ERROR`. Validate uploads by content (`utils/images.py`).
- Authorization on every route (see AGENTS.md rule 3). Check ownership with `auth.ensure_self_or_admin`. Admin-only routers use `dependencies=[Depends(auth.require_admin)]`.
- Use `get_db` dependencies; commit explicitly; on `IntegrityError` roll back and translate to a 4xx with a Spanish message from `messages.py`.
- Dates: server-local naive datetimes (`TZ` set); use `seasons.current()` / `seasons.of()`; never compute a season by hand and never write `season`.
- Use SQLAlchemy 2 style queries; parametrize everything, never format user input into SQL. Raw SQL is acceptable only in migrations (with bound params for values).
- Pin new dependencies in `requirements.txt` with `==`. Keep `api` and `bot` requirements independent.
- Blocking or long work (RAWG sync, mass achievement checks) goes to `BackgroundTasks`/scheduler, not inline in a request.
- The scheduler is single-process: keep jobs idempotent and recorded in `job_runs`.

## Front (JavaScript)

- Vanilla ES modules, `type: module`, ESLint rules in `eslint.config.js` (`eqeqeq`, `prefer-const`, `no-var`, unused vars error, `_` prefix to ignore args).
- Markup only via `html` tagged template + `mount(el, html`...`)`. Interpolated values are escaped; to embed already-safe markup use `raw()` (and `mount`/`append`) from `html.js`, never string concatenation into `innerHTML`.
- All HTTP through `js/lib/api.js` (`api(path, options)`); it adds the token and handles 401. Do not call `fetch` directly for the API.
- Keep pure logic in `js/lib/` or a pure module of the page (e.g. `home/sessions.js`) and unit test it in `front/tests/` with `node:test`.
- One stylesheet per area in `css/`; reuse existing classes/variables from `base.css` before adding new ones. Mobile first (it is a PWA).
- Accessibility: real `<button>`/`<label>`, keyboard reachable modals (`ui/modal.js`), toasts via `ui/toast.js`.

## Bot

Read-only (except `/activate`, see architecture), generic endpoints only. Texts live in `bot/src/utils/messages.py`. Handle the API being down or the token expiring (`Config.request` already retries on 401). Any new write capability is a design decision, not an implementation detail.

## Database and migrations

- **All rules live in [migrations.md](migrations.md) and are mandatory.** In short: every schema change ships with a migration, applied migrations are immutable, history is linear, migrations are idempotent and abort on inconsistent data, and they are verified on an empty DB and on the previous revision with data.
- Keep the emergency `admin` and `app_settings` seeding logic in code, not in migrations.

## Tests

- API: `unittest`, files `api/tests/test_*.py`, importing `src.*` (run from `api/`). Mock time by passing `now` explicitly; mock `requests`/Telegram/the AI providers, never call real services.
- Front: `node --test`, files `front/tests/*.test.js`.
- A bug fix comes with a test that fails without it whenever the logic is testable.

## Recipes

### Add an API endpoint

1. Schema in `database/schemas.py` (request/response).
2. DB access in `crud/<area>.py`, rules in `utils/` if cross-entity.
3. Route in `routers/<area>.py` with auth dependency, `response_model`, status code, Spanish error messages from `utils/messages.py`.
4. If the router is new: add `include_router` in `main.py`.
5. Tests for the pure part; update `README.md`/`docs/architecture.md` if the behaviour is a documented rule.
6. Use it from the front via `api()` (and from the bot only if it is read-only).

### Add or change a column / table

1. Edit `database/models.py`.
2. Create the migration following [migrations.md](migrations.md) (`alembic revision -m "..." --rev-id NNN_name`, defensive style of 008/009) and complete its verification checklist.
3. Update schemas/crud/routers that expose it.
4. Verify on a clean DB and on a DB at the previous revision with data (checklist in migrations.md).
5. If it is a derived value, make it a `Computed` column like `season` rather than storing it.

### Add an admin panel section

Backend under `routers/manage.py` (already admin-only). Front: a module in `front/js/pages/admin/`, wired in `admin/index.js`, reusing `components.js`, `form.js`, `dialogs.js`; styles in `css/admin.css`.

### Add a page to the front

Create `js/pages/<name>/index.js` following the page contract (`active`, `render`, `dispose`), register the prefix in `ROUTES` in `js/main.js`, add the navbar item in `ui/layout.js`, and a stylesheet linked from `index.html` if needed.

### Add a scheduled job

Write the async job in `utils/scheduler.py`, expose a pure slot function and add it to `tick()` with a grace window; results are recorded in `job_runs` by `_run`. Add unit tests for the slot/due logic. Configurable schedule values go in `app_settings` (`utils/settings.py`: define key, default and `coerce` validation; then the panel form).

### Add a runtime setting

Define it in `utils/settings.py` (key, default, coercion/validation, secret or not), expose it via `GET/PUT /manage/settings`, add the field in `front/js/pages/admin/settings.js`, and cover `coerce` with a test. Secrets must be encrypted and write-only from the panel.

### Add an environment variable

Read it in `api/src/config.py` (or `bot/src/utils/config.py`), add a placeholder to `.env.template` with a comment, mention it in `README.md` if operators must know, and never give it a real default that is a secret.

### Add a notification / announcement

Event-driven: hook it in `utils/actions.py` where the event happens, respecting the notifications switches in `app_settings` (general, admin-alerts) and the `silent` flag used by manual edits. Texts in Spanish.

### Add a dependency

Pin the exact version, justify it in the commit message, and check it supports Python 3.13 (api) / 3.11 (bot) or Node 20+. Prefer the standard library. Rebuild the image to verify.

## Definition of done

- Tests pass (`api` unittest, `front` `npm test`), front lint clean.
- Stack builds and starts (`docker compose up -d --build`); if a migration is involved, its full checklist in [migrations.md](migrations.md) is done.
- Docs updated (`README.md`, `docs/`, `.env.template`) when behaviour, config or architecture changed.
- No secrets, dumps or generated files committed.
