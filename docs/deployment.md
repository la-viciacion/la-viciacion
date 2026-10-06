# Deployment and operations

How to install, configure, deploy and operate the stack. The settings that go in `.env` are described in [configuration.md](configuration.md); what the application does at run time is in [features.md](features.md). This page also covers what a maintainer needs to know when changing the stack.

## Installing

The stack is four services orchestrated by `docker-compose.yml`: `laviciacion-db` (MariaDB), `laviciacion-api` (FastAPI), `laviciacion-bot` (the Telegram bot) and `laviciacion-front` (the PWA). The API's container runs `alembic upgrade head` automatically on every start (see `api/entrypoint.sh`) before serving requests, so schema migrations are never a manual step — and `laviciacion-api` won't even start until `laviciacion-db` reports healthy (`depends_on` + a MariaDB healthcheck), so a slow first boot doesn't race the migration.

**Publishing is switched off for now** (the repository variable `PUBLISH_IMAGES` is not `true`, see [CI/CD](#cicd)): a server builds the images from its checkout, as the on-demand deploy does. When it is on, the images are published to GHCR (`ghcr.io/la-viciacion/laviciacion-api`, `-front` and `-bot`) every time a `vX.Y.Z` tag is created, so a server does not need to build anything: `docker compose pull && docker compose up -d` is the whole deploy. `LAVI_VERSION` in `.env` pins a release (e.g. `2.0.0`; default `latest`). Nothing sensitive or environment-specific is inside them: the API and the bot read `.env` through `env_file`, and the front's nginx receives only `API_UPSTREAM` (default `http://laviciacion-api:5000`) and `DNS_RESOLVER` (default `127.0.0.11`), both optional. `docker compose up -d --build` builds the same images from the `Dockerfile`s instead, which is what development uses (see [Images](#images)).

### Fresh install (no existing data)

```bash
docker compose pull && docker compose up -d     # the published images
# or, to build from this checkout:  docker compose up -d --build
```

> If `pull` answers `denied`, the package is still private: on GitHub, *Packages* → the package → *Package settings* → *Change visibility* → Public (once per image; the repository is public).

> **Windows (Docker Desktop):** add `DB_DATA=laviciacion_db_data` to `.env` before the first start (see `.env.template`), so the database lives in a Docker volume instead of `./db/data`. On that folder MariaDB 12+ cannot rebuild tables and the migrations fail. On Linux leave it unset. Details and tested versions: [Database storage](#database-storage-linux-vs-windows).

MariaDB starts with an empty database and the API's `alembic upgrade head` builds the whole schema from scratch (migration `000_baseline_v1` creates the starting tables, the rest run in order, and `015_seed_platforms` adds a default list of platforms). On start the API also creates the `admin` user from `GOD_ADMIN_PASS`, the achievements and the push keys. Nothing else to do: fill in `.env` and run it.

### Importing a pre-v2 database into a new environment

Deploying v2 to a *new* environment from a backup taken on the old (Clockify-based, "v1") schema — for example right before cutting over in production — needs the database to be seeded with that backup **before** the API applies its migrations, so the historical data survives the migration instead of starting from an empty schema:

1. Put your pre-migration `mysqldump` file in `db/init/` (e.g. `db/init/laviciacion-backup.sql`). Anything ending in `.sql`, `.sql.gz` or `.sh` placed there is picked up.
2. Make sure `db/data/` is empty/does not exist yet — MariaDB's official image only runs the scripts in `db/init/` **the first time it initializes a data directory**. If `db/data/` already has data (e.g. you're re-running this on an environment that already started once), the import is silently skipped; remove/rename `db/data/` first if you need a clean re-import.
3. Bring the stack up:
   ```bash
   docker compose pull && docker compose up -d
   ```
   On first boot MariaDB imports the backup file(s) from `db/init/`, then (once healthy) `laviciacion-api` starts and runs `alembic upgrade head`, bringing that imported v1 schema up to the current one — including the one-off data cleanup migration that backfills missing `games_statistics` rows and patches any orphaned Clockify project references found in *that specific backup*.
4. Check it went well:
   ```bash
   docker compose logs laviciacion-db   # look for the SQL import log lines
   docker compose logs laviciacion-api  # look for "Running upgrade ..." lines from alembic, no errors
   ```
5. Nothing to recompute: totals, rankings and streaks are computed from the sessions whenever they are requested. (Optional) Use **Recalcular logros…** in the admin panel so the achievements of the imported history are worked out for every season right away: nothing re-checks them by itself, only a stopped timer, a change to sessions or library entries, or that button.

`db/init/` itself is tracked (so it always exists on a fresh clone), but the SQL/backup files you drop into it are gitignored — never commit a real database dump.

## Stack

Docker Compose, four containers on the `la-viciacion` network:

| Container | Image / build | Ports | Notes |
|---|---|---|---|
| `laviciacion-front` | `ghcr.io/la-viciacion/laviciacion-front` (built from `front/Dockerfile`: `nginx:1.31-alpine`, static files copied in) | `3000` | Proxies `/api/` to `API_UPSTREAM`; gzip for text and JSON; `no-cache` on html/js/css, one day for `/assets/`; SPA fallback to `index.html` |
| `laviciacion-api` | `ghcr.io/la-viciacion/laviciacion-api` (`api/Dockerfile`: `python:3.14-slim-trixie`) | `127.0.0.1:5000` | `entrypoint.sh`: wait for DB → `alembic upgrade head` → `uvicorn` (`--proxy-headers`) |
| `laviciacion-bot` | `ghcr.io/la-viciacion/laviciacion-bot` (`bot/Dockerfile`: `python:3.14-slim-trixie`) | none | Depends on the API; restarts itself when Telegram settings change |
| `laviciacion-db` | `mariadb:12.3.3` (official, pinned) | `127.0.0.1:3307` | Healthcheck gates the API start; data in `./db/data` (or a named volume, see [Database storage](#database-storage-linux-vs-windows)) |

All use `restart: unless-stopped`. API, bot and db read `.env` through `env_file`; the front gets only `API_UPSTREAM` and `DNS_RESOLVER` through `environment:` (it must not see the secrets in `.env`). Logs of api/bot are bind-mounted to `./api/logs` and `./bot/logs`.

## Images

The compose file names the three images (`image: ghcr.io/la-viciacion/laviciacion-<service>:${LAVI_VERSION:-latest}`) and also has their `build:` context, so one file serves both uses: `docker compose pull && docker compose up -d` runs the published images (production), `docker compose up -d --build` builds them from the Dockerfiles and tags them with the same names (development). The database uses the official `mariadb` image. `docker-compose.dev.yml` (an override, see [development.md](development.md#run-the-stack)) builds the same services from the checkout under `*-dev` image and container names.

**An image contains no configuration and no secrets, and must keep it that way** (the release workflow fails otherwise): everything that differs between environments is a run-time variable. The front's nginx config is a template (`front/nginx.conf.template`) that the nginx image renders at start (`envsubst`) with `API_UPSTREAM` and `DNS_RESOLVER`; only those two are substituted (`NGINX_ENVSUBST_FILTER`), the rest of nginx's own `$variables` are untouched. Adding another deploy-time value to the front means: a variable in the template, a default `ENV` in `front/Dockerfile`, the entry in `docker-compose.yml` and `.env.template` (and in `EXTERNAL` of `api/tests/test_env_template.py`).

## Configuration

Single `.env` (template: `.env.template`; every variable and what it does: [configuration.md](configuration.md)). Production checklist:

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

`docker-compose.yml` pins **`mariadb:12.3.3`**, the LTS series (supported until June 2029). It used to be `image: mariadb`, which follows whatever is newest at pull time: today that is 13.0, a *rolling* release with a short life, and a server that has pulled once keeps its image until the next `docker compose pull`, so two environments could silently run different versions. The tag is exact on purpose; patch releases of 12.3 arrive as Dependabot pull requests (the compose ecosystem is limited to patches), tested before they are merged.

How the pin is enforced:

- **CI tests the pinned version.** `checks.yml` reads the tag from `docker-compose.yml` and runs the MariaDB tests on that image, and `test_mariadb_pinned_version.py` fails if the server that answered is not that version. What is tested and what is deployed cannot drift apart.
- **A weekly run (`mariadb-versions.yml`, Mondays) tests the moving tags `lts` and `latest`.** It is an early warning, not a gate: if MariaDB releases something that breaks a migration, you know before having to move to it, and pull requests never turn red because of an upstream release.
- `test_deployment_pins.py` fails if the compose file loses its tag or a Dockerfile starts from an untagged image.

What was tested (a v1 backup migrated from scratch to the head, then the API started):

| MariaDB | Data on `./db/data` (bind mount) | Data on a named volume |
|---|---|---|
| 11.8.9 | works (Windows/Docker Desktop) | not tested |
| **12.3.3 (pinned)** | **fails at migration 012** (Windows/Docker Desktop); Linux VPS: expected to work, as in CI | works (migrations, v1 upgrade and boot test, 2026-10-02) |
| 13.0.2 | **fails at migration 012** (Windows/Docker Desktop) | works |
| `latest`, untagged (Linux VPS, 2026-09-30) | works | not needed |

The Windows failure is specific to Docker Desktop's `9p/drvfs` share, not to MariaDB 12+ in general: the Linux VPS deployed on 2026-09-30 came up without problems. Its symptom is the API looping with `OperationalError: (1025, "Error on rename of './<db>/users_games' to './<db>/#sql-backup-...' (errno: 194 "Tablespace is missing for a table")` while the db log says `InnoDB: Cannot rename ... because the source file does not exist`. It is not a data or migration bug: the fix is `DB_DATA` (above) on Windows.

Rules of thumb:

- **Never change the version of a database that already has data by editing the image.** MariaDB does not support downgrading a data directory: **a directory created by 13.0 cannot be opened by 12.3** (the container refuses to start), and the other way round after a rollback is not safe either. Move between versions with a `mariadb-dump` and an empty data directory: `docker compose down`, remove the volume (or empty `./db/data`), put the dump in `db/init/` and start. A dump taken on 13.0.2 loaded into 12.3.3 without errors (tested 2026-10-02 with the synthetic v1 database migrated to the head: same tables, rows and collations, and `alembic upgrade head` was a no-op); older-into-newer is the supported direction, so try a restore before relying on the opposite one.
- **Changing the series is a decision, not an update.** To move to another LTS: change the tag in `docker-compose.yml`, let CI run (it tests exactly that), and migrate the data with a dump as above. Dependabot never proposes a series change.
- Tables created by migrations 002, 009, 013 and 014 take the server's default collation, which differs between MariaDB versions (it was `utf8mb4_uca1400_ai_ci` on 13.0); the v1 tables and `game_timers.game_id` are `utf8mb4_general_ci`. A foreign key needs both columns to have the same collation, so `016` converts `game_timers.platform` to match `platform_tags.id`; keep it in mind before comparing schemas of different servers.

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
### Migration 019 (game ratings) drops a column

`019_game_scores` creates `game_scores` and **drops `users_games.score` without copying it** (a decision of the data's owner: ratings start from zero; the old column was only ever written by the admin panel and the app never read it). Back up first; the downgrade brings the column back empty.

- Front and API are deployed together; keep API changes backwards compatible with the previously cached front where feasible (the front is revalidated on every load, so mismatch windows are short).

## Backups and restore

```bash
# backup
docker compose exec laviciacion-db sh -c 'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines "$MARIADB_DATABASE"' > backup-$(date +%F).sql
```

The admin panel can also take one: **Sistema → Copia de seguridad → Descargar copia (.sql.gz)** (`POST /manage/backup`, admins only, written to the audit log). The API writes it itself (`api/src/utils/sql_dump.py`, no `mariadb-dump` in the image): for each table `DROP TABLE IF EXISTS`, the server's own `SHOW CREATE TABLE` and the rows as `INSERT`s, read in one consistent snapshot, `alembic_version` included. It is served gzipped because the images (`BLOB` columns) are written as hex, which doubles their size in plain text; the compressed file is about the size of the `mariadb-dump` one. It restores the same way as the dump above (the `mariadb` client into an empty database, `gunzip -c backup.sql.gz | mariadb ...`, or `db/init/`, which accepts `.sql.gz` as it is, so there is no need to unpack it). It is a convenience for a quick copy, not a replacement for the command above before a deploy with a migration: it holds no routines, triggers or events (the schema has none) and it is as sensitive as the database (password hashes, avatars, encrypted tokens), so keep it out of the repo and do not share it.

Backups (`*.sql`, `*.sql.gz`, `*.dump`) are gitignored; store them outside the repo. To restore into a fresh environment, put the dump in `db/init/` with an empty `db/data/` ([Importing a pre-v2 database](#importing-a-pre-v2-database-into-a-new-environment) explains the first-boot import), or import it into a running DB with a normal `mariadb` client.

## Rollback

Code rollback: set `LAVI_VERSION` in `.env` to the previous release (e.g. `2.0.0`), then `docker compose pull && docker compose up -d` (the previous code works on the schema after `015`/`016`; what it did that the keys forbid, such as storing a session of a game that does not exist, would now fail instead of being stored). If a migration was applied, either restore the pre-deploy backup or run `alembic downgrade` only when that migration defines a real downgrade. Prefer restore from backup for anything destructive.

## Health

`GET /api/v1/keepalive` is the lightweight liveness endpoint (excluded from request logs). The DB has a compose healthcheck. There is no external monitoring beyond optional Sentry.

## CI/CD

`.github/workflows/ci.yml` runs the checks on every PR to `main` (not again after the merge, see [workflow.md](workflow.md#nothing-is-run-twice)). The checks live in `checks.yml`, which `release.yml` reuses with no narrowing, so a release is gated by everything a PR could be gated by. `release.yml` runs when a tag `vX.Y.Z` is pushed (or by hand from the Actions tab, which does everything but publish):

1. **checks** (`checks.yml`, always the full set here): **api-tests**, **bot-tests** (Python 3.14) and **front-tests** (tests and lint), as separate parallel jobs. The API tests need only dummy values for the variables of `config.py` (set in the `env` of `checks.yml` and of `mariadb-tests.yml`, which does not inherit it; when you add a required variable to `config.py`, add it to both) and the `.env.template` at the repo root.
   **build**: builds the three images and looks inside each one: no `.env*`, `*.sql`, `*.dump` under `/app` or the web root, and no credential-looking variable baked in (`PASS`, `SECRET`, `TOKEN`, `KEY`).
2. **publish** (tags only, and only while the repository variable `PUBLISH_IMAGES` is `true`; it is not set for now, so a tag is checked but nothing is published): pushes `ghcr.io/la-viciacion/laviciacion-{api,front,bot}` tagged `X.Y.Z`, `X.Y` and `latest` (prereleases get no `latest`), using the workflow's own `GITHUB_TOKEN`; no secret has to be configured.

The tag is also the version the app reports: `release.yml` (or the prod deploy, which builds the tag on the server) passes it to the API image as the build arg `APP_VERSION` (`ENV APP_VERSION`), `GET /api/v1/utils/version` returns it to any logged-in user and the side menu shows it, small and centred, under "Cerrar sesión". An image built from a checkout (`docker compose up --build`) reports `dev`. It is not in any file of the repo, so it cannot drift from the tag.

Cut a release with `git tag v2.0.0 && git push origin v2.0.0` (see [roadmap](roadmap.md): tags are not created until 2.0.0 ships). To start publishing, set the variable (Settings → Secrets and variables → Actions → Variables, `PUBLISH_IMAGES` = `true`) before pushing the tag; the first time, set each package public (see [Installing](#installing)); the repository is public, so nothing needs a login afterwards. The images are `linux/amd64` only.

### Deploying from GitHub

`.github/workflows/deploy.yml` deploys on demand (nothing deploys on merge): Actions tab → *Deploy* → *Run workflow* on `main`, choosing the `target`. `dev` runs whatever `main` is (every commit there came from a PR with a green `CI`). `prod` first checks that the **Release images** run of the tag passed on the commit the tag points to, and stops otherwise: wait for that run after pushing the tag. It connects over SSH and the server does the work, so nothing about the server's layout lives in the workflow.

| Target | What the server does | Key (repository secret) |
|---|---|---|
| `dev` | `deploy.sh` in the dev checkout: `git pull --ff-only` and `up -d --build` with the `*-dev` override | `DEPLOY_SSH_KEY_DEV` |
| `prod` | a script outside the repo: checks out the release tag in the prod checkout, builds the images from it and runs `up -d` (the base compose file only, so the containers keep the prod names) | `DEPLOY_SSH_KEY_PROD` |

`version` (prod only) is `latest`, meaning the newest stable `vX.Y.Z` tag, or an explicit `X.Y.Z`; deploying an older one is also the rollback. The tag must exist on GitHub (the server fetches tags) but its images do not: the server builds them, so the release workflow publishing to GHCR is not needed for a deploy. The build runs before `up`, so a build failure leaves what is running untouched.

- **One key per target.** A user without a password (`laviciacion-deploy`) in the `docker` and project groups has two entries in `authorized_keys`, each restricted to one command: `command="/path/to/dev/deploy.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA...` and the same with `command="/usr/local/bin/laviciacion-deploy-prod"` for the prod key. Even if a key leaks it can only run its script. Each job of the workflow reads only its own key.
- **The prod script is owned by root and kept outside the repo**, so neither a `git pull` nor the deploy user can change what the key runs. It reads the version from `SSH_ORIGINAL_COMMAND`, accepts only `latest` or `X.Y.Z`, takes a lock, `git fetch --tags`, checks out `v<version>` detached, exports `LAVI_VERSION` (the version the app reports and the tag of the local images), runs `docker compose build --build-arg APP_VERSION=...` and then `up -d --remove-orphans`. Every step runs under `set -euo pipefail`, so a failure turns the job red.
- **Prod is a second checkout** next to the dev one (for example `la-viciacion-prod`) with its own `.env`: different `FRONT_/API_/DB_HOST_PORT`, its own `DB_DATA` volume and its own Telegram bot token (two bots with one token fight over the updates). The container names (`laviciacion-*` against `*-dev`) and the compose project (the directory name) already keep the stacks apart.
- **GitHub side**: five **repository** secrets: `DEPLOY_SSH_KEY_DEV` and `DEPLOY_SSH_KEY_PROD` (the private keys), and `DEPLOY_HOST`, `DEPLOY_USER` and `DEPLOY_KNOWN_HOSTS` (`<host> ssh-ed25519 AAAA...`, the host key read from the server, so the connection cannot be intercepted), shared by both. The workflow declares no `environment:` because GitHub Free ignores environments, their secrets and their required reviewers in a private repository; this way nothing changes if the repository is made private. The price is that a prod deploy has no approval step: `target` defaults to `dev`, and both jobs refuse to run from any branch but `main`. While the repository is public (or on a plan with environments), moving each key into an environment with *Required reviewers* restores the approval.
- **If the repository is private**, the server also needs read access to it for `git fetch`: a read-only deploy key (Settings → Deploy keys) for the user that runs the deploy scripts, and the `origin` of both checkouts switched from HTTPS to SSH.
- Migrations still run on API start, so **take a backup before deploying a change with a migration** (see [Backups and restore](#backups-and-restore)); the deploy does not take one.
- Rotate a key by replacing its public key in `authorized_keys` and the matching `DEPLOY_SSH_KEY_*` secret.
