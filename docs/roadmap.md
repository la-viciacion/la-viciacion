# Roadmap and pending decisions

## Pending until 2.0.0 is released

These are deliberately **undefined for now**. Do not invent or enforce them; when 2.0.0 ships, decide and document them here and in `AGENTS.md`. (The branch workflow is decided: see [workflow.md](workflow.md).)

- **Versioning and releases**: the app version is **2.0.0** (set in `front/package.json` and its lockfile). A dedicated `VERSION` file may become the single source of truth when GitHub CI creates releases; until then the API version in `main.py` (`0.1.0`, shown in the OpenAPI docs) is still a placeholder to align with it. Tags, changelog format and release notes are still open.
- **Commit conventions**: enforced only on the PR title (it becomes the squash commit); no changelog tooling yet.
- **CI/CD**: checks run on every PR and on `main`, and gate the release workflow (see [deployment.md](deployment.md#cicd)). Open: automatic deployment, `arm64` images.

Until then: no tags or releases.

## Known debt / candidate improvements

- **Push notifications, next steps** (the wiring exists, see README): design how long messages (rankings) and images (achievements) fit into a push (short text + opening the relevant page, `image` in the payload, per-event titles); decide whether the weekly summary should also reach users without a Telegram id (`_weekly_summary` still skips them); test on real Android and iOS devices before deploying it (it is on by default). The running-timer notification reaches every subscribed device of the user: decide whether it needs its own per-device switch (a `push_subscriptions` column, like `receive_group`) or an "off" value for the refresh interval, and check on a real Android phone how it behaves with the screen off (Doze may delay the refreshes).

- MariaDB-backed tests cover the migrations and the schema rules (`api/tests/test_mariadb_*.py`). A synthetic v1 database walks the whole chain (`test_mariadb_v1_upgrade.py`). Still missing: API-level tests on MariaDB (timers/manual-session rules, authorization through real requests), more refusal cases (008, 011, 016) and an `alembic check` parity guard (today it has pre-existing noise, see the checklist).
- **MariaDB version policy:** the compose file does not pin the image (`image: mariadb`), so it drifts to the latest major. 12+ breaks table rebuilds on a Windows bind mount (worked around with `DB_DATA`, see [deployment.md](deployment.md#mariadb-version)). The Linux server runs latest with a bind mount and works (2026-09-30), so the open point is only whether to pin a version to avoid surprise major upgrades of a database that has data.
- The bot only tests its access rules (`bot/tests/test_access.py`); the handlers have no tests.
- A new deployment ends with empty `_archived_*` tables (migration 005 renames the v1 `*_historical` tables that 000 had to create). Harmless; a migration that drops the archives that are empty would tidy it up.
- `utils/email.py` is kept for the upcoming e-mail features; nothing calls it yet.
- `crud/users.py` (~1300 lines) and `utils/actions.py` are large; split by responsibility when touched.
- Sentry `traces_sample_rate`/`profiles_sample_rate` are 1.0; tune for production.
