# Database migrations (Alembic)

**This is the most delicate part of the project.** A bad migration can corrupt or lose data that cannot be recovered, and MariaDB cannot roll back DDL (each `ALTER`/`CREATE`/`DROP` commits immediately). Every rule here exists for that reason. If a task touches migrations and something in this page is unclear or conflicts with the task, **stop and ask**.

## Ground rules

1. **Alembic is the only schema authority.** Any change to `api/src/database/models.py` that affects the schema ships with a migration in the same change. Nobody edits the DB by hand, and nobody relies on `create_all` (it exists in `main.py` only as a leftover; see [roadmap](roadmap.md)).
2. **Applied migrations are immutable.** Never edit, rename, renumber, reorder or delete a migration that may have run anywhere (any dev copy of the DB, staging, production). Fix forward with a new migration. Editing is allowed only for a migration that has never left your working tree, and only before it is committed/pushed.
3. **Linear history, a single head.** No branches, no merge revisions, no branch labels. If two changes both add a migration, the second one is rebased onto the first (renumber it and change its `down_revision` *before* it is ever applied anywhere).
4. **Never run a migration against production without a fresh, verified backup** (see [deployment](deployment.md#backups-and-restore)). Migrations run automatically on API start, so *deploying* is *migrating*.
5. **Never delete data silently.** Dropping a column/table, narrowing a type or adding a constraint that can fail requires an explicit decision recorded in the migration docstring, and a backup.
6. **Never rewrite data to make a constraint pass.** If existing rows violate the new rule, the migration must **abort with a clear message** telling the operator what to fix (migration 008 and 009 are the model). Auto-"fixing" is a decision for a human.
7. **No agent runs migrations against a database it does not fully own** (production, the user's real data in `db/data/`) without explicit confirmation in that conversation. Generating and reviewing migration files is fine; applying them to real data is the user's call.

## Conventions

- **File**: `api/alembic/versions/NNN_short_name.py`, `NNN` = next three-digit number, no gaps.
- **Revision id**: `NNN_short_name`, **at most 32 characters** (the `alembic_version.version_num` column is `VARCHAR(32)`; a longer id fails at the very end of the migration, leaving the DDL applied but the version unrecorded). It must start with the same `NNN_` as the file. Note the id can be shorter than the filename slug (e.g. `008_season_generated` in `008_season_as_generated_column.py`).
- **`down_revision`** is the id of the previous migration. The first one is `None`.
- **Docstring** (mandatory): what changes and *why*, what data it touches, what it refuses to do, and whether/how the downgrade works and what it loses.
- Create it with an explicit id so the naming is right:

  ```bash
  cd api
  alembic revision -m "short description" --rev-id 010_short_name
  ```

  `file_template` in `alembic.ini` produces `010_short_name_short_description.py`; rename the file to `010_short_name.py`-style if the slug is too long, keeping the `NNN_` prefix. `tests/test_migrations.py` enforces the naming and the chain.

## How to write one

Use `api/alembic/versions/008_season_as_generated_column.py` and `009_settings_jobs_telegram_unique.py` as the reference. The required style:

- **Idempotent and re-runnable.** Inspect the current state (tables, columns, indexes, generated expressions via `sa.inspect(bind)` / `information_schema`) before every step and skip what is already done. A migration interrupted halfway must be safe to run again.
- **Verify before you change.** First phase: read-only checks of every assumption (duplicates, NULLs, inconsistent values, orphan references). Raise `RuntimeError` with an actionable message (which rows, how to find them). Second phase: apply changes.
- **Order matters**: backfill/clean → add/replace columns → add constraints and indexes last (a failing unique key must not leave the schema half-changed with the data already altered).
- **Explicit SQL for MariaDB-specific things** (generated columns, `MODIFY`, index changes). Bind parameters for any value; never format data into SQL. Identifiers come only from constants in the file.
- **No imports from `src.*` models or crud** inside migrations: they change over time and would make old migrations behave differently. Define the tables/columns you need inline (`sa.table(...)`) or use plain SQL.
- **Data migrations are separate from schema migrations** when they are non-trivial, so each can be reasoned about and, if needed, re-run alone.
- **Downgrade**: implement it whenever it can be done without inventing data, and say in the docstring what it cannot restore. If it is genuinely impossible (destructive upgrade), `downgrade()` must `raise RuntimeError("irreversible: restore the pre-migration backup")` rather than silently doing nothing.
- **Large tables**: prefer operations that do not rebuild the table (e.g. `VIRTUAL` generated columns), and say so.
- **Autogenerate is a draft, never the result.** `alembic revision --autogenerate` may be used to get a starting point, but the output must be reviewed line by line: it misses generated columns, server defaults and renames (it emits drop+add, which **loses data**), and produces noise from type comparison.

## Verification checklist (all mandatory before considering a migration done)

Use a throwaway database (a scratch compose stack or a separate MariaDB), **never** `db/data/` with real data.

0. Start a throwaway MariaDB of the same image as production, e.g. `docker run -d --name mig-test-db -e MARIADB_ROOT_PASSWORD=... -p 127.0.0.1:3399:3306 mariadb`, and load a dump of the real database into it (`mariadb-dump` from `laviciacion-db`, read-only). Point the env (`MARIADB_HOST=127.0.0.1:3399`, ...) at it. Delete the container and the dump afterwards; dumps contain real user data.
1. `cd api && python -m unittest discover -s tests -t .`: `tests/test_migrations.py` must pass (single head, linear, naming, ≤ 32 chars, docstring, `upgrade`/`downgrade` present). It needs `alembic` installed (`pip install -r requirements.txt`).
2. **Empty DB → head**: start from nothing, `alembic upgrade head` succeeds.
3. **Previous revision → head**: a DB at the previous revision *with realistic data* upgrades cleanly. Ideally also a copy of the latest production backup restored into the scratch DB.
4. **Re-run**: run `alembic upgrade head` again (no-op) and, for the new migration, simulate an interruption (apply half by hand or run the steps twice); it must converge.
5. **Constraint refusals**: with data that violates the new rule, it aborts with the message and leaves the DB untouched.
6. **Downgrade** (if defined): `alembic downgrade -1` then `upgrade head` again.
7. **Model parity**: run `alembic check` before and after your migration on the same scratch DB. It is not clean today (pre-existing noise: the `_archived_*` tables, `ix_game_timers_*` indexes, `LONGBLOB` vs `LargeBinary`), so what matters is that your migration adds **no new** differences.
8. The API starts and the affected flows work against the migrated DB.
9. Docs updated: README/`docs/architecture.md` if the data model or a domain rule changed.

## Operating migrations

```bash
# from inside the API container or with the env set locally
alembic current                # revision the DB is at
alembic history --verbose
alembic upgrade head           # what entrypoint.sh runs on every API start
alembic downgrade -1           # only if that migration defines a real downgrade
alembic stamp <id>             # DANGEROUS: rewrites the recorded version without running anything
```

- `alembic stamp` and manual edits of `alembic_version` are last-resort recovery tools; never use them without understanding the exact DB state and without a backup.
- If `upgrade head` fails in production: **do not retry blindly and do not `stamp`**. Read the error, inspect which steps were applied (the migrations are idempotent, so a re-run after fixing the cause converges), or restore the pre-deploy backup. The API container will keep restarting until the migration succeeds (`entrypoint.sh` uses `set -e`), which is intentional: the app never runs on a half-migrated schema.
- `entrypoint.sh` waits up to 60 s for the DB before migrating; a fresh import of a large backup can take longer than the MariaDB healthcheck suggests.
- Importing a pre-v2 backup (`db/init/`) relies on migrations 001–010 handling that legacy schema; do not "simplify" old migrations.

## Forbidden

- Editing/renumbering/deleting applied migrations; squashing history without an explicit plan and a tested equivalence.
- Multiple heads, merge migrations, branch labels.
- Importing application models/crud into a migration.
- Data-fixing to satisfy a constraint without aborting first.
- `alembic stamp`, `DROP DATABASE`, truncating tables, or `downgrade base` against real data.
- Running migrations on production data from an automated agent without explicit user approval in that conversation.
