# Roadmap and pending decisions

## Pending until 2.0.0 is released

These are deliberately **undefined for now**. Do not invent or enforce them; when 2.0.0 ships, decide and document them here and in `AGENTS.md`. (The branch workflow is decided: see [workflow.md](workflow.md).)

- **Versioning and releases**: the app version is **2.0.0** (set in `front/package.json` and its lockfile). A dedicated `VERSION` file may become the single source of truth when GitHub CI creates releases; until then the API version in `main.py` (`0.1.0`, shown in the OpenAPI docs) is still a placeholder to align with it. Tags, changelog format and release notes are still open.
- **Commit conventions**: enforced only on the PR title (it becomes the squash commit); no changelog tooling yet.
- **CI/CD**: checks run on every PR and on `main`, and gate the release workflow (see [deployment.md](deployment.md#cicd)). Open: automatic deployment, `arm64` images.

Until then: no tags or releases.

## Known debt / candidate improvements

- **Push notifications, next steps** (the wiring exists, see README): design how long messages (rankings) and images (achievements) fit into a push (short text + opening the relevant page, `image` in the payload, per-event titles); decide whether the weekly summary should also reach users without a Telegram id (`_weekly_summary` still skips them); test on real Android and iOS devices before deploying it (it is on by default). The running-timer notification reaches every subscribed device of the user: decide whether it needs its own per-device switch (a `push_subscriptions` column, like `receive_group`) or an "off" value for the refresh interval, and check on a real Android phone how it behaves with the screen off (Doze may delay the refreshes).

- MariaDB-backed tests cover the migrations step by step, a synthetic v1 database, the schema rules, model parity and every route of the API, the admin panel included, through real requests (`api/tests/test_mariadb_*.py`, a few minutes because every alembic call boots the app). Still missing: more refusal cases for the migrations (008, 011, 016), the bot handlers and the untested front pages.
- The downgrade of `008_season_generated` fails on MariaDB (`MODIFY` on a generated column, error 1907) and migrations 001-005 cannot be re-run. Both are applied and immutable (listed in `test_mariadb_migration_chain.py`); the way back in production is the pre-deploy backup.
- **Next MariaDB LTS:** the image is pinned to 12.3.3 (LTS, supported until June 2029; see [deployment.md](deployment.md#mariadb-version)). Plan the move to the following LTS before then, with a dump and an empty data directory, and let the weekly `mariadb-versions.yml` run tell whether `latest` already passes. Dev databases created with the old untagged image (13.0) must be recreated from a dump.
- A new deployment ends with empty `_archived_*` tables (migration 005 renames the v1 `*_historical` tables that 000 had to create). Harmless; a migration that drops the archives that are empty would tidy it up.
- `utils/email.py` is kept for the upcoming e-mail features; nothing calls it yet.
- `crud/users.py` (~1300 lines) and `utils/actions.py` are large; split by responsibility when touched.
- Sentry `traces_sample_rate`/`profiles_sample_rate` are 1.0; tune for production.
- **Front pages without DOM tests:** the pure logic and the libraries are tested, but the rendering and the event wiring of the pages (about 3,500 lines under `front/js/pages` and `front/js/ui`) need a DOM. Decide whether to add `jsdom` as a dev dependency (it is not a build step or a framework, but it is a dependency) or keep extracting pure functions; the paths the pages call are already checked against the API (`api/tests/test_front_api_paths.py`).
