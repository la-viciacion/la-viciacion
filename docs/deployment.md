# Deployment and operations

The operator-facing procedure (fresh install and importing a pre-v2 backup) is in the [README](../README.md#deployment-docker-compose). This page adds what an agent or maintainer needs to know when changing the stack.

## Stack

Docker Compose, four containers on the `la-viciacion` network:

| Container | Image / build | Ports | Notes |
|---|---|---|---|
| `laviciacion-front` | `ghcr.io/la-viciacion/laviciacion-front` (built from `front/Dockerfile`: `nginx:alpine`, static files copied in) | `3000` | Proxies `/api/` to `API_UPSTREAM`; `no-cache` on html/js/css; SPA fallback to `index.html` |
| `laviciacion-api` | `ghcr.io/la-viciacion/laviciacion-api` (`api/Dockerfile`: `python:3.13-slim-bookworm`) | `127.0.0.1:5000` | `entrypoint.sh`: wait for DB → `alembic upgrade head` → `uvicorn` (`--proxy-headers`) |
| `laviciacion-bot` | `ghcr.io/la-viciacion/laviciacion-bot` (`bot/Dockerfile`: `python:3.11-slim-bookworm`) | none | Depends on the API; restarts itself when Telegram settings change |
| `laviciacion-db` | `mariadb` (official) | `127.0.0.1:3307` | Healthcheck gates the API start; data in `./db/data` (or a named volume, see [Database storage](#database-storage-linux-vs-windows)) |

All use `restart: unless-stopped`. API, bot and db read `.env` through `env_file`; the front gets only `API_UPSTREAM` and `DNS_RESOLVER` through `environment:` (it must not see the secrets in `.env`). Logs of api/bot are bind-mounted to `./api/logs` and `./bot/logs`.

## Images

The compose file names the three images (`image: ghcr.io/la-viciacion/laviciacion-<service>:${LAVI_VERSION:-latest}`) and also has their `build:` context, so one file serves both uses: `docker compose pull && docker compose up -d` runs the published images (production), `docker compose up -d --build` builds them from the Dockerfiles and tags them with the same names (development). The database uses the official `mariadb` image. `docker-compose.dev.yml` (an override, see [development.md](development.md#run-the-stack)) builds the same services from the checkout under `*-dev` image and container names.

**An image contains no configuration and no secrets, and must keep it that way** (the release workflow fails otherwise): everything that differs between environments is a run-time variable. The front's nginx config is a template (`front/nginx.conf.template`) that the nginx image renders at start (`envsubst`) with `API_UPSTREAM` and `DNS_RESOLVER`; only those two are substituted (`NGINX_ENVSUBST_FILTER`), the rest of nginx's own `$variables` are untouched. Adding another deploy-time value to the front means: a variable in the template, a default `ENV` in `front/Dockerfile`, the entry in `docker-compose.yml` and `.env.template` (and in `EXTERNAL` of `api/tests/test_env_template.py`).

## Configuration

Single `.env` (template: `.env.template`). Production checklist:

- Strong unique values for `GOD_ADMIN_PASS`, `SECRET_KEY`, `MARIADB_*`.
- `CORS_ORIGINS` is a JSON list with the real public origin(s).
- `TZ` set (drives the current season and the scheduled job times).
- `ENVIRONMENT=production`; Sentry DSNs if wanted.
- Password recovery (optional) needs `PUBLIC_URL` (the public address of the app, e.g. `https://lavi.example.com`) and an SMTP server: `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_EMAIL` (From), `SMTP_USER`/`SMTP_PASS`. Without them the feature answers "not configured". Migration `017_password_resets` adds its table. Try it once after deploying: the **Correo** card of the admin panel (Sistema) shows the state and sends a test email to your own account (your admin user needs an email); then ask for a link from the login page. Check the spam folder of a new sender.
- Push notifications (optional) need HTTPS in front of the app; their VAPID keys are generated from the panel, not set in `.env`.
- `SECRET_KEY` also derives the key that encrypts the Telegram token: rotate it only if you can re-enter the token from the panel (it invalidates all sessions too).

## Database storage (Linux vs Windows)

`DB_DATA` in `.env` chooses where MariaDB keeps its files (`docker-compose.yml`, db service):

- **Unset (default): `./db/data`**, a bind mount. It is what a Linux server (the VPS) uses, and the data is visible on disk.
- **`DB_DATA=laviciacion_db_data`: a Docker named volume.** Use it on **Windows (Docker Desktop)**. There `./db/data` is a `9p/drvfs` share on which MariaDB 12+ cannot rebuild a table (InnoDB cannot rename the `.ibd` of a table it is rebuilding), so migrations such as `012_drop_derived_stats` fail with `errno 194 "Tablespace is missing for a table"` (verified 2026-09-30: MariaDB 11.8 works on the bind mount, 12.3 and 13.0 fail, 13.0 works on a named volume). Any future migration that rebuilds a table would hit it too.

With a named volume the data is not in the repo folder: take backups with `mariadb-dump` (see below). To move an existing Windows database to the volume: dump it, `docker compose down`, set `DB_DATA`, start the stack with an empty volume and import the dump (or drop it in `db/init/` for the first boot). The Linux/VPS setup does not need any change.

### MariaDB version

`docker-compose.yml` uses `image: mariadb` without a tag, so a rebuild or a pull moves to whatever the latest release is (13.0 at the time of writing). What was tested (2026-09-30, a v1 backup migrated from scratch to `016_foreign_keys`, then the API started):

| MariaDB | Data on `./db/data` (bind mount) | Data on a named volume |
|---|---|---|
| 11.8.9 | works (Windows/Docker Desktop) | not tested |
| 12.3.3 | **fails at migration 012** (Windows/Docker Desktop) | not tested |
| 13.0.2 | **fails at migration 012** (Windows/Docker Desktop) | works |
| latest, untagged (Linux VPS) | works (production, 2026-09-30) | not needed |

**Linux server (the production VPS), `image: mariadb` without a tag (the latest release at deploy time), data on the `./db/data` bind mount: works.** The code-review release (migrations `015` and `016` included) was deployed there on 2026-09-30 and came up without problems. So the failure below is specific to Docker Desktop on Windows, not to MariaDB 12+ in general. The symptom of the Windows problem is the API looping with `OperationalError: (1025, "Error on rename of './<db>/users_games' to './<db>/#sql-backup-...' (errno: 194 "Tablespace is missing for a table")` while the db log says `InnoDB: Cannot rename ... because the source file does not exist`. It is not a data or migration bug: the fix is `DB_DATA` (above) on Windows.

Rules of thumb:

- **Do not change the major version of a database that already has data by editing the image.** MariaDB does not support downgrading a data directory: going from 13 back to 11.8 (or the other way after a rollback) may refuse to start. Move between versions with a `mariadb-dump` and an empty data directory.
- Tables created by migrations 002, 009, 013 and 014 take the server's default collation, which differs between MariaDB versions (it was `utf8mb4_uca1400_ai_ci` on 13.0); the v1 tables and `game_timers.game_id` are `utf8mb4_general_ci`. A foreign key needs both columns to have the same collation, so `016` converts `game_timers.platform` to match `platform_tags.id`; keep it in mind before comparing string columns of different tables.
- To pin a version, set `image: mariadb:11.8` (LTS) in the compose file. Decide it once for all environments; see [roadmap](roadmap.md).

## TLS and exposure

The compose file publishes the front on `:3000` (plain HTTP, every interface) and the API/DB only on localhost. The host side of each port is set in `.env`: `FRONT_HOST_IP` / `FRONT_HOST_PORT`, `API_HOST_IP` / `API_HOST_PORT`, `DB_HOST_IP` / `DB_HOST_PORT` (the containers keep 3000, 5000 and 3306), e.g. `FRONT_HOST_IP=10.0.0.2` to expose the front only on the server's internal address. TLS termination and the public domain are expected to be handled by a reverse proxy in front of the front container (not part of this repo). Do not publish the DB or the API directly.

## Deploying a change

```bash
git pull                                 # the compose file and docs; the code comes in the images
docker compose pull                      # the release set in LAVI_VERSION (default: latest)
docker compose up -d                     # recreates the containers whose image changed
docker compose logs --tail=100 laviciacion-api   # look for "Running upgrade ..." and no errors
```

Migrations run automatically on API start, so a deploy that includes a migration is one step. Consequences to keep in mind:

- Take a DB backup **before** deploying a migration (see below); read [migrations.md](migrations.md#operating-migrations) for what to do if it fails. If the API container loops on restart, the migration is failing: check the logs, do not stamp.
- The API is a single replica (in-process scheduler). Do not scale it horizontally.

### Deploying the v2 migrations (000-016) onto an existing database

The first deploy of the code-review release (2026-09-30) runs `015_seed_platforms` and `016_foreign_keys` on your data (`000_baseline_v1` does nothing when the tables exist). Before it:

1. **Back up** (see below). This is the only way back: `000` cannot be downgraded and `016` only drops its keys.
2. Deploy as usual and read `docker compose logs -f laviciacion-api`.
3. `015` adds a default list of platforms **only if `platform_tags` is empty**; a database with platforms is untouched.
4. `016` adds the foreign keys (sessions, library entries and achievements point at users, games, platforms and achievements; push devices go with their user). **If some row points at something that no longer exists, the migration aborts without changing anything** and the API container keeps restarting (`restart: unless-stopped`) until the data is fixed. The log lists, per column, how many rows, some of the offending values and the `SELECT` that shows them. Typical causes: a game or user deleted by hand, a platform renamed or removed, a session with an empty `game_id`. Fix them (point them at the right record or delete them, your call: the migration never does it for you), and the next restart applies it. `docker compose logs laviciacion-api | grep -A12 "Cannot add the foreign keys"` finds the report.
5. Healthy signs: `Running upgrade 014_user_settings -> 015_seed_platforms`, `... -> 016_foreign_keys`, then `Scheduler started` and `GET /api/v1/` answering.

After `016` the database rejects what used to be kept by hand: deleting a user or a game that still has sessions, library entries or achievements fails (the admin panel already asks for confirmation and removes them first).
- Front and API are deployed together; keep API changes backwards compatible with the previously cached front where feasible (the front is revalidated on every load, so mismatch windows are short).

## Backups and restore

```bash
# backup
docker compose exec laviciacion-db sh -c 'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines "$MARIADB_DATABASE"' > backup-$(date +%F).sql
```

Backups (`*.sql`, `*.sql.gz`, `*.dump`) are gitignored; store them outside the repo. To restore into a fresh environment, put the dump in `db/init/` with an empty `db/data/` (README explains the first-boot import), or import it into a running DB with a normal `mariadb` client.

## Rollback

Code rollback: set `LAVI_VERSION` in `.env` to the previous release (e.g. `2.0.0`), then `docker compose pull && docker compose up -d` (the previous code works on the schema after `015`/`016`; what it did that the keys forbid, such as storing a session of a game that does not exist, would now fail instead of being stored). If a migration was applied, either restore the pre-deploy backup or run `alembic downgrade` only when that migration defines a real downgrade. Prefer restore from backup for anything destructive.

## Health

`GET /api/v1/keepalive` is the lightweight liveness endpoint (excluded from request logs). The DB has a compose healthcheck. There is no external monitoring beyond optional Sentry.

## CI/CD

`.github/workflows/ci.yml` runs the checks on every PR to `main` and after each merge (see [workflow.md](workflow.md)). The checks live in `checks.yml`, which `release.yml` reuses, so a release is gated by exactly what gates a PR. `release.yml` runs when a tag `vX.Y.Z` is pushed (or by hand from the Actions tab, which does everything but publish):

1. **checks** (`checks.yml`): **tests**: API (Python 3.13), bot (3.11), front tests and lint. The API tests need only dummy values for the variables of `config.py` (set in the workflow's `env`; when you add a required variable to `config.py`, add it there too) and the `.env.template` at the repo root.
   **build**: builds the three images and looks inside each one: no `.env*`, `*.sql`, `*.dump` under `/app` or the web root, and no credential-looking variable baked in (`PASS`, `SECRET`, `TOKEN`, `KEY`).
2. **publish** (tags only): pushes `ghcr.io/la-viciacion/laviciacion-{api,front,bot}` tagged `X.Y.Z`, `X.Y` and `latest` (prereleases get no `latest`), using the workflow's own `GITHUB_TOKEN`; no secret has to be configured.

Cut a release with `git tag v2.0.0 && git push origin v2.0.0` (see [roadmap](roadmap.md): tags are not created until 2.0.0 ships). The first time, set each package public (README, Deployment); the repository is public, so nothing needs a login afterwards. There is no automatic deploy: the server pulls when you decide. The images are `linux/amd64` only.
