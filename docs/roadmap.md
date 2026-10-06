# Roadmap and pending decisions

## Pending until 2.0.0 is released

These are deliberately **undefined for now**. Do not invent or enforce them; when 2.0.0 ships, decide and document them here and in `AGENTS.md`. (The branch workflow is decided: see [workflow.md](workflow.md).)

- **Versioning and releases**: the version of the app is the `vX.Y.Z` tag, injected into the API image at build time (`APP_VERSION`, see [deployment.md](deployment.md)); no file holds it (`front/package.json` still says `2.0.0` but nothing reads it). Changelog format and release notes are still open.
- **Commit conventions**: enforced only on the PR title (it becomes the squash commit); no changelog tooling yet.
- **CI/CD**: checks run on every PR (not again on `main`) and in full on every tag, and the prod deploy requires that tag run to have passed (see [deployment.md](deployment.md#cicd)). Open: automatic deployment, `arm64` images, and the cost items below.

Until then: no tags or releases.

## CI cost

The CI repeats nothing between a PR and `main` any more (see [workflow.md](workflow.md#nothing-is-run-twice)). What is left, from most to least worth doing, if the minutes of Actions ever become a limit (a run takes ~3.5 min in the clock and ~5.5 min of work, ~13 billed because each job is rounded up to the minute; before the MariaDB job was split it was ~155-190 s of it):

1. **Build the images on a PR only when something that goes into them changes** (`Dockerfile`, `requirements.txt`, `package*.json`, `.dockerignore`, `nginx`); the tag builds them all anyway.
2. **Fewer, bigger jobs.** `bot-tests`, `front-tests`, `mariadb-image`, `changes` and `pr-title` take seconds each and are billed a minute each; grouping them saves ~5 billed minutes per run.
3. **Publish what was checked.** When `PUBLISH_IMAGES` is on, `release.yml` builds each image twice (once in `build`, once in `publish`); the second hits the cache but could push the first.
4. **The weekly `lts` run** overlaps the pinned one while `docker-compose.yml` pins the newest patch of the LTS; drop it if it never says anything the pinned run did not.
5. **Candidates inside the MariaDB tests**, to remove only with evidence they never catch anything: `UpgradeFromAnOlderRevisionTests` in `test_mariadb_migrations.py` goes through the same migrations as the v1 chain tests with a different seed, and the two classes of `test_mariadb_migration_v1_upgrade.py` that refuse a duplicated e-mail or Telegram id overlap the refusal cases of `test_mariadb_migration_refusals.py` in mechanism, not in data.

## Known debt / candidate improvements

- **Push notifications, next steps** (the wiring exists, see [features.md](features.md#push-notifications-installed-pwa)): design how long messages (rankings) and images (achievements) fit into a push (short text + opening the relevant page, `image` in the payload, per-event titles); decide whether the weekly summary should also reach users without a Telegram id (`_weekly_summary` still skips them); test on real Android and iOS devices before deploying it (it is on by default). The running-timer notification reaches every subscribed device of the user: decide whether it needs its own per-device switch (a `push_subscriptions` column, like `receive_group`) or an "off" value for the refresh interval, and check on a real Android phone how it behaves with the screen off (Doze may delay the refreshes).

- MariaDB-backed tests cover the migrations step by step, a synthetic v1 database, the schema rules, model parity and every route of the API, the admin panel included, through real requests (`api/tests/test_mariadb_*.py`, a few minutes because every alembic call boots the app). Still missing: DOM tests for the rest of the front pages (see below).
- The downgrade of `008_season_generated` fails on MariaDB (`MODIFY` on a generated column, error 1907) and migrations 001-005 cannot be re-run. Both are applied and immutable (listed in `test_mariadb_migration_chain.py`); the way back in production is the pre-deploy backup.
- **Next MariaDB LTS:** the image is pinned to 12.3.3 (LTS, supported until June 2029; see [deployment.md](deployment.md#mariadb-version)). Plan the move to the following LTS before then, with a dump and an empty data directory, and let the weekly `mariadb-versions.yml` run tell whether `latest` already passes. Dev databases created with the old untagged image (13.0) must be recreated from a dump.
- A new deployment ends with empty `_archived_*` tables (migration 005 renames the v1 `*_historical` tables that 000 had to create). Harmless; a migration that drops the archives that are empty would tidy it up.
- `utils/email.py` is kept for the upcoming e-mail features; nothing calls it yet.
- `crud/users.py` (~1300 lines) and `utils/actions.py` are large; split by responsibility when touched.
- Sentry `traces_sample_rate`/`profiles_sample_rate` are 1.0; tune for production.
- **Front pages without DOM tests:** the home history, the game picker and the modal and toast are tested against jsdom (`front/tests/*.dom.test.js`, helpers in `front/tests/dom.js`); the rest of `front/js/pages` and `front/js/ui` (timer card, sessions and completion windows, profile and its library, admin panel, login and recovery) is not. Add them page by page when touching each one; the paths the pages call are already checked against the API (`api/tests/test_front_api_paths.py`).
