# Deployment and operations

The operator-facing procedure (fresh install and importing a pre-v2 backup) is in the [README](../README.md#deployment-docker-compose). This page adds what an agent or maintainer needs to know when changing the stack.

## Stack

Docker Compose, four containers on the `la-viciacion` network:

| Container | Image / build | Ports | Notes |
|---|---|---|---|
| `laviciacion-front` | `front/Dockerfile` (`nginx:alpine`, static files copied in) | `3000` | Proxies `/api/` to the API; `no-cache` on html/js/css; SPA fallback to `index.html` |
| `laviciacion-api` | `api/Dockerfile` (`python:3.13-slim-bookworm`) | `127.0.0.1:5000` | `entrypoint.sh`: wait for DB → `alembic upgrade head` → `uvicorn` (`--proxy-headers`) |
| `laviciacion-bot` | `bot/Dockerfile` (`python:3.11-slim-bookworm`) | none | Depends on the API; restarts itself when Telegram settings change |
| `laviciacion-db` | `mariadb` (official) | `127.0.0.1:3307` | Healthcheck gates the API start; data in `./db/data` (or a named volume, see [Database storage](#database-storage-linux-vs-windows)) |

All use `restart: unless-stopped` and read `.env` through `env_file` (front excepted). Logs of api/bot are bind-mounted to `./api/logs` and `./bot/logs`.

## Configuration

Single `.env` (template: `.env.template`). Production checklist:

- Strong unique values for `GOD_ADMIN_PASS`, `SECRET_KEY`, `INVITATION_KEY`, `MARIADB_*`.
- `CORS_ORIGINS` is a JSON list with the real public origin(s).
- `TZ` set (drives the current season and the scheduled job times).
- `ENVIRONMENT=production`; Sentry DSNs if wanted.
- Push notifications (optional) need HTTPS in front of the app; their VAPID keys are generated from the panel, not set in `.env`.
- `SECRET_KEY` also derives the key that encrypts the Telegram token: rotate it only if you can re-enter the token from the panel (it invalidates all sessions too).

## Database storage (Linux vs Windows)

`DB_DATA` in `.env` chooses where MariaDB keeps its files (`docker-compose.yml`, db service):

- **Unset (default): `./db/data`**, a bind mount. It is what a Linux server (the VPS) uses, and the data is visible on disk.
- **`DB_DATA=laviciacion_db_data`: a Docker named volume.** Use it on **Windows (Docker Desktop)**. There `./db/data` is a `9p/drvfs` share on which MariaDB 12+ cannot rebuild a table (InnoDB cannot rename the `.ibd` of a table it is rebuilding), so migrations such as `012_drop_derived_stats` fail with `errno 194 "Tablespace is missing for a table"` (verified 2026-09-30: MariaDB 11.8 works on the bind mount, 12.3 and 13.0 fail, 13.0 works on a named volume). Any future migration that rebuilds a table would hit it too.

With a named volume the data is not in the repo folder: take backups with `mariadb-dump` (see below). To move an existing Windows database to the volume: dump it, `docker compose down`, set `DB_DATA`, start the stack with an empty volume and import the dump (or drop it in `db/init/` for the first boot). The Linux/VPS setup does not need any change.

## TLS and exposure

The compose file publishes the front on `:3000` (plain HTTP) and the API/DB only on localhost. TLS termination and the public domain are expected to be handled by a reverse proxy in front of the front container (not part of this repo). Do not publish the DB or the API directly.

## Deploying a change

```bash
git pull
docker compose up -d --build            # rebuilds changed images, recreates containers
docker compose logs --tail=100 laviciacion-api   # look for "Running upgrade ..." and no errors
```

Migrations run automatically on API start, so a deploy that includes a migration is one step. Consequences to keep in mind:

- Take a DB backup **before** deploying a migration (see below); read [migrations.md](migrations.md#operating-migrations) for what to do if it fails. If the API container loops on restart, the migration is failing: check the logs, do not stamp.
- The API is a single replica (in-process scheduler). Do not scale it horizontally.
- Front and API are deployed together; keep API changes backwards compatible with the previously cached front where feasible (the front is revalidated on every load, so mismatch windows are short).

## Backups and restore

```bash
# backup
docker compose exec laviciacion-db sh -c 'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines "$MARIADB_DATABASE"' > backup-$(date +%F).sql
```

Backups (`*.sql`, `*.sql.gz`, `*.dump`) are gitignored; store them outside the repo. To restore into a fresh environment, put the dump in `db/init/` with an empty `db/data/` (README explains the first-boot import), or import it into a running DB with a normal `mariadb` client.

## Rollback

Code rollback: check out the previous revision and `docker compose up -d --build`. If a migration was applied, either restore the pre-deploy backup or run `alembic downgrade` only when that migration defines a real downgrade. Prefer restore from backup for anything destructive.

## Health

`GET /api/v1/keepalive` is the lightweight liveness endpoint (excluded from request logs). The DB has a compose healthcheck. There is no external monitoring beyond optional Sentry.

## CI/CD

None yet. See [roadmap.md](roadmap.md).
