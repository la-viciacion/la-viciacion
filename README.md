# La Viciación

## Basic config

### Environment

Copy `.env.template` to `.env` and fill in your values. That single file is read by every service (`api`, `bot` and `db`) through `env_file` in `docker-compose.yml`; when running the api or bot outside Docker they fall back to that same `.env`. Variables already present in the environment always win over the file.

`docker-compose.yml` and the `Dockerfile`s are ready to use as they are; they contain no secrets.

### Webhooks

Copy `api/src/routers/webhooks_template.py` to `api/src/routers/webhooks.py`. This file allows to create your own 'public' webhooks if you need. So, you can create an endpoint like `/tBn7NyNHAsP9WjP3sJUXglxaTATJxrfs3J2DauBV5fthwuGKq3le`, and call directly from another service without authentication like the `bot` routes (to execute other processes).

### OpenAI integration

If you want to use OpenAI integration (adding your API key to .env file), you need to copy `api/src/utils/ai_prompts_template.py` to `api/src/utils/ai_prompts.py`. Then, you could adjust the prompts for the predefined notifications.

## Deployment (Docker Compose)

The stack is four services orchestrated by `docker-compose.yml`: `laviciacion-db` (MariaDB), `laviciacion-api` (FastAPI), `laviciacion-bot` (the Telegram bot) and `laviciacion-front` (the PWA). The API's container runs `alembic upgrade head` automatically on every start (see `api/entrypoint.sh`) before serving requests, so schema migrations are never a manual step — and `laviciacion-api` won't even start until `laviciacion-db` reports healthy (`depends_on` + a MariaDB healthcheck), so a slow first boot doesn't race the migration.

### Fresh install (no existing data)

```bash
docker compose up -d --build
```

MariaDB starts with an empty database, and the API's `alembic upgrade head` creates the schema from scratch (all migrations run in order). Nothing else to do.

### Migrating an existing (pre-v2) database into a new environment

Deploying v2 to a *new* environment from a backup taken on the old (Clockify-based, "v1") schema — for example right before cutting over in production — needs the database to be seeded with that backup **before** the API applies its migrations, so the historical data survives the migration instead of starting from an empty schema:

1. Put your pre-migration `mysqldump` file in `db/init/` (e.g. `db/init/laviciacion-backup.sql`). Anything ending in `.sql`, `.sql.gz` or `.sh` placed there is picked up.
2. Make sure `db/data/` is empty/does not exist yet — MariaDB's official image only runs the scripts in `db/init/` **the first time it initializes a data directory**. If `db/data/` already has data (e.g. you're re-running this on an environment that already started once), the import is silently skipped; remove/rename `db/data/` first if you need a clean re-import.
3. Bring the stack up:
   ```bash
   docker compose up -d --build
   ```
   On first boot MariaDB imports the backup file(s) from `db/init/`, then (once healthy) `laviciacion-api` starts and runs `alembic upgrade head`, bringing that imported v1 schema up to the current one — including the one-off data cleanup migration that backfills missing `games_statistics` rows and patches any orphaned Clockify project references found in *that specific backup*.
4. Check it went well:
   ```bash
   docker compose logs laviciacion-db   # look for the SQL import log lines
   docker compose logs laviciacion-api  # look for "Running upgrade ..." lines from alembic, no errors
   ```
5. (Optional) Trigger one manual recompute so rankings/statistics reflect the imported history immediately, instead of waiting for the next scheduled sync:
   ```bash
   curl -H "x-api-key: <API_KEY from .env>" "http://localhost:5000/api/v1/admin/sync-data?sync_all=true"
   ```

`db/init/` itself is tracked (so it always exists on a fresh clone), but the SQL/backup files you drop into it are gitignored — never commit a real database dump.
