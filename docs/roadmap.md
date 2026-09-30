# Roadmap and pending decisions

## Pending until 2.0.0 is released

These are deliberately **undefined for now**. Do not invent or enforce them; when 2.0.0 ships, decide and document them here and in `AGENTS.md`.

- **Branch workflow**: branch naming, which branch is the integration branch (`main`, `develop` and `2.0` exist today), PR/merge policy, protected branches.
- **Versioning and releases**: the app version is **2.0.0** (set in `front/package.json` and its lockfile). A dedicated `VERSION` file may become the single source of truth when GitHub CI creates releases; until then the API version in `main.py` (`0.1.0`, shown in the OpenAPI docs) is still a placeholder to align with it. Tags, changelog format and release notes are still open.
- **Commit conventions enforcement**: Conventional Commits are used informally; no tooling enforces them.
- **CI/CD**: no pipeline yet (tests, lint, image build, deployment).

Until then: work on the current branch, small commits, no tags or releases.

## Known debt / candidate improvements

- **Push notifications, next steps** (the wiring exists, see README): design how long messages (rankings) and images (achievements) fit into a push (short text + opening the relevant page, `image` in the payload, per-event titles); decide whether the weekly summary should also reach users without a Telegram id (`_weekly_summary` still skips them); test on real Android and iOS devices before enabling it in production.

- **A completely empty database cannot be migrated**: migration 001 alters `games`, which only exists in a v1 backup, so `alembic upgrade head` fails on a fresh install (found 2026-09-29 while testing 010; the README claims the opposite). Needs a baseline (e.g. an idempotent `000` creating the v1 tables) or a documented bootstrap. Until then the only supported path is importing a v1/current dump.

- No DB-backed API tests: add integration tests against a throwaway MariaDB (migrations from empty and from previous revision, timers/manual-session rules, authorization). Today only the static integrity of the Alembic history is tested automatically; the DB-backed steps of the [migrations checklist](migrations.md#verification-checklist-all-mandatory-before-considering-a-migration-done) are manual.
- `main.py` still runs `create_all` at import, which can create tables behind Alembic's back; remove it once a migration-only bootstrap is verified.
- The bot has no tests.
- `platform_tags` (the platform catalogue) can only be edited by hand in the DB and its ids are the old Clockify tag ids; add an admin panel section to manage platforms.
- `POST /signup` (with `INVITATION_KEY`) is not used by the front yet (admins create accounts); accounts created through it are active from the start.
- `utils/email.py` is kept for the upcoming e-mail features; nothing calls it yet.
- `crud/users.py` (~1300 lines) and `utils/actions.py` are large; split by responsibility when touched.
- Sentry `traces_sample_rate`/`profiles_sample_rate` are 1.0; tune for production.
- Public sign-up is parked (admins create accounts).
