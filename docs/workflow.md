# Git workflow

Simplified trunk-based development for a team of 2-3. `main` is the trunk: always green and releasable.

## Rules

1. **Nobody pushes to `main`.** Every change goes through a pull request (branch protection enforces it, also for admins).
2. **Short-lived branches** off `main`, named `<type>/<short-description>` (`feat/ranking-filters`, `fix/timer-stop`, `docs/workflow`). Aim to merge within a day or two; if a feature is bigger, split it into steps that are each safe to merge (behind a setting or not yet reachable from the UI).
3. **Small PRs.** One concern per PR; do not mix refactors with behaviour changes.
4. **The PR title is the commit.** PRs are **squash-merged**, so the title must follow Conventional Commits (`feat(front): ...`, types in `AGENTS.md`); CI checks it. Commits inside the branch can be messy.
5. **Merge when**: the `CI` check is green, the approvals the ruleset asks for are there (none while there is a single maintainer, one from the second person on), and the branch is up to date with `main`. Delete the branch after merging (GitHub does it automatically).
6. **Review turnaround**: aim to review within a working day. With 2 people the reviewer is simply the other one; do not self-approve.
7. **Releases** are tags `vX.Y.Z` cut from `main` (see [deployment.md](deployment.md#cicd)). There is no `develop` and no release branch; a hotfix is a normal PR to `main` followed by a new tag.

## What CI checks

`.github/workflows/ci.yml` runs on every PR and again on `main` after the merge. The required status is the single job **`CI`**, which passes only if every check that applies to the change passes (see [Which checks run for a change](#which-checks-run-for-a-change)). The checks live in `checks.yml`, the same ones that gate a release:

- API tests (Python 3.14), including the Alembic history guards, the endpoint security list and the `.env.template` check.
- Migrations and schema rules on a real MariaDB (empty database to head, an older revision with data to head, re-run, downgrade, generated `season` columns, constraints), on the exact image `docker-compose.yml` pins (CI reads the tag from there and a test checks the server really is that version). A weekly run (`mariadb-versions.yml`) tries the moving tags `lts` and `latest` as an early warning; it never blocks a PR.
- The API boots on a freshly migrated MariaDB (`test_mariadb_app_boot.py`): every route the routers declare is published under `/api/v1` and answers 401 without a token (except the reviewed public ones), the docs are hidden, and startup seeds the database.
- Bot tests (Python 3.14).
- Front tests and ESLint.
- The three Docker images build and contain no secrets, data or baked-in credentials.
- The PR title follows Conventional Commits.

### Which checks run for a change

A pull request only runs the checks its files can affect; `main` after a merge, the release workflow and the weekly runs always run everything. `ci.yml` starts with a `changes` job that lists the PR's files (GitHub API) and hands them to `.github/scripts/ci_scope.py`, which answers with the checks to run (`api-tests`, `bot-tests`, `front-tests`, `mariadb`) and the images to build. The single required job `CI` counts a skipped job as passed, so a PR that touches only docs shows just `pr-title`, `changes` and `CI`.

| The change touches | Runs |
|---|---|
| `docs/`, `design/`, `*.md` at the root, `LICENSE`, `.gitignore`, `.gitattributes`, the PR template, `dependabot.yml` | nothing but the PR title |
| `front/` | front tests and lint, front image; plus the API tests when it is `front/js/` or `front/Dockerfile` (a test reads them) |
| `api/` | API tests, MariaDB tests, API image |
| `bot/src/` | bot tests, bot image, API tests and MariaDB tests (the contract test and the `.env.template` check read the bot's code) |
| `bot/` (tests, requirements...) | bot tests, bot image |
| `.env.template`, `docker-compose.dev.yml` | API tests |
| `docker-compose.yml` | API tests and MariaDB tests (it pins the version they run on) |
| anything else (`.github/workflows/`, `.github/scripts/`, a new top-level path...) | **everything** |

Three safeguards keep this honest. The default is to run everything: only the paths listed as inert run nothing, so a new directory or file is never silently skipped. The script is read from the base branch, so a PR cannot change the rules that judge it (changing the script is itself a change that runs everything). And `api/tests/test_ci_scope.py` pins the table above and fails if an API test starts reading a directory the script does not know about. When you add a test that reads files outside its own directory, add that path to `RULES` in `ci_scope.py` and to the table.

To force the full run on a PR, touch a path that runs everything or run the **Release images** workflow by hand (it does everything but publish).

Run the same locally before pushing: see [development.md](development.md#tests-and-lint).

## Dependency updates

`.github/dependabot.yml` opens one grouped PR per week and ecosystem, each on its own weekday (Monday api, Tuesday bot, Wednesday front, Thursday Actions, Friday base images) so they rarely coexist. Majors of Python packages and npm libraries arrive as separate PRs on purpose; the Python version of the images is not bumped automatically (it must match the CI jobs). The MariaDB image in `docker-compose.yml` only receives patch releases of the pinned series (Fridays); changing the series is a data decision (see [deployment.md](deployment.md#mariadb-version)).

- **A green Dependabot PR is not a reviewed one.** Read what it bumps. CI only proves what the tests exercise: FastAPI 0.141 passed every test and still could not start the API, until a test that boots the application was added. When a bump slips past CI, add the test that would have caught it.
- **Never auto-merge them.** One person reads the changelog of what changes (especially 0.x libraries such as FastAPI, whose minors can break) and merges.
- **Branches must be up to date** (see below), so after merging one PR another that is still open may be behind `main`. Comment `@dependabot rebase` on it (or press "Update branch") and wait for CI again. Dependabot only rebases by itself when there is a conflict.
- To skip a bump on purpose: `@dependabot ignore this minor version` (or this dependency), or add an `ignore` entry to the config with the reason.

## One-time repository setup (GitHub settings)

Settings → Rules → Rulesets (or Branches → Branch protection rule) for `main`:

- Require a pull request before merging; dismiss stale approvals on new pushes.
- Require status checks to pass: select **`CI`**; require the branch to be up to date.
- Approvals: **0 while there is a single maintainer**; raise it to 1 when the second person joins (then nobody can approve their own PR). No bypass actors, and no `update` restriction rule (it would also stop merges made through PRs).
- Block force pushes and deletion.
- Do not allow bypassing (applies to admins too).

Settings → General → Pull Requests:

- Allow **squash merging** only, default message "Pull request title".
- Automatically delete head branches.
