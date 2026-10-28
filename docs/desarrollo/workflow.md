# Git workflow

Simplified trunk-based development for a team of 2-3. `main` is the trunk: always green and releasable.

## Rules

1. **Nobody pushes to `main`.** Every change goes through a pull request (branch protection enforces it, also for admins).
2. **Short-lived branches** off `main`, named `<type>/<short-description>` (`feat/ranking-filters`, `fix/timer-stop`, `docs/desarrollo/workflow`). Aim to merge within a day or two; if a feature is bigger, split it into steps that are each safe to merge (behind a setting or not yet reachable from the UI).
3. **Small PRs.** One concern per PR; do not mix refactors with behaviour changes. Several related or tiny changes may travel together as a [batch](#batching-changes), as long as each one is its own atomic commit.
4. **Every commit lands on `main`.** PRs are **rebase-merged** (a trial, see [roadmap.md](roadmap.md)): each commit of the branch is replayed on `main` as it is, so each one must be atomic, green on its own, and follow Conventional Commits (`feat(front): ...`, types in `AGENTS.md`). The PR title follows the same format, and CI checks the title and the subject of every commit (merge commits are skipped). If it fails, fix the messages with `git rebase -i` and `git push --force-with-lease`; squash `fixup!` commits first. No "wip" or "fix typo" commits.
5. **Merge when**: the `CI` check is green, the approvals the ruleset asks for are there (none while there is a single maintainer, one from the second person on), and the branch is up to date with `main`. Delete the branch after merging (GitHub does it automatically).
6. **Review turnaround**: aim to review within a working day. With 2 people the reviewer is simply the other one; do not self-approve.
7. **Releases** are tags `vX.Y.Z` cut from `main` (see [deployment.md](deployment.md#cicd)). There is no `develop` and no release branch; a hotfix is a normal PR to `main` followed by a new tag.

## Batching changes

CI runs when a pull request exists (`ci.yml` listens to `pull_request` only), never on a plain push, so a branch costs nothing until its PR is opened. Every PR that is ready and every push to an open PR starts a run of ~4-5 minutes. To pay for that once instead of many times:

1. **Open the PR when the work is finished, not before.** Push the branch as often as you like meanwhile (backup, another machine, a second pair of eyes); do not keep pushing to an open PR step by step, each push restarts the checks (the previous run is cancelled).
2. **Group related or small changes into one PR**, one atomic commit per change. The merge is a rebase, so `main` receives the commits one by one with their own Conventional Commit messages and each can still be reverted alone. The PR title summarises the batch (`feat: ...`, `chore: ...`) and CI checks it and every commit subject as usual.
3. **Independent pieces of work on separate branches** (no PR yet) are brought together at the end on a fresh branch off `main`, in a linear way (a merge commit would be dropped by the rebase merge):

   ```bash
   git switch -c batch/<what> main
   git cherry-pick main..feat/first
   git cherry-pick main..feat/second
   ```

   Open one PR from `batch/<what>`, and delete the original branches (they never had a PR). CI runs the union of the checks that the files of all the commits need, once.
4. **What a batch costs**: one failing change blocks the rest until it is fixed, and review and CI are not per change. Cherry-picking branches that touched the same files can conflict: if that is likely, do them one after another on the same branch. Keep a change out of the batch when it is risky, urgent (a hotfix) or needs its own review.

## What CI checks

`.github/workflows/ci.yml` runs on every PR; **`main` is not tested again after the merge** (see [Nothing is run twice](#nothing-is-run-twice)). The required status is the single job **`CI`**, which passes only if every check that applies to the change passes (see [Which checks run for a change](#which-checks-run-for-a-change)). The checks live in `checks.yml`, the same ones that gate a release:

- API tests (Python 3.14), including the Alembic history guards, the endpoint security list and the `.env.template` check.
- Migrations and schema rules on a real MariaDB (every migration one by one on a v1 database, re-run, downgrade, an older revision with data to head, models matching the schema, generated `season` columns, constraints), on the exact image `docker-compose.yml` pins (CI reads the tag from there and a test checks the server really is that version). A weekly run (`mariadb-versions.yml`) tries the moving tags `lts` and `latest` as an early warning; it never blocks a PR.
- The API boots on a freshly migrated MariaDB (`test_mariadb_app_boot.py`): every route the routers declare is published under `/api/v1` and answers 401 without a token (except the reviewed public ones), the docs are hidden, and startup seeds the database.
- Bot tests (Python 3.14).
- Front tests and ESLint.
- The three Docker images build and contain no secrets, data or baked-in credentials.
- The PR title and the subject of every commit follow Conventional Commits.

### Which checks run for a change

A pull request only runs the checks its files can affect; the release workflow (on a tag) and the weekly runs always run everything. `ci.yml` starts with a `changes` job that lists the PR's files (GitHub API) and hands them to `.github/scripts/ci_scope.py`, which answers with the checks to run (`api-tests`, `bot-tests`, `front-tests`, `mariadb`) and the images to build. The single required job `CI` counts a skipped job as passed, so a PR that touches only a README shows just `pr-title`, `changes` and `CI`.

| The change touches | Runs |
|---|---|
| `design/`, `docs-demo/`, `*.md` at the root, `LICENSE`, `.gitignore`, `.gitattributes`, the PR template, `dependabot.yml` | nothing but the PR title |
| `docs/`, `mkdocs.yml`, `requirements-docs.txt`, `docs.yml` | the documentation build (`mkdocs build --strict`: a broken link or a missing page blocks the merge) |
| `docs/guia-usuario/` | also the API tests (one of them checks that the topics of the chat's help name pages of the guide that exist) |
| `front/` | front tests and lint, front image; plus the API tests when it is `front/js/` or `front/Dockerfile` (a test reads them) |
| `api/` | API tests, MariaDB tests, API image |
| `bot/src/` | bot tests, bot image, API tests and MariaDB tests (the contract test and the `.env.template` check read the bot's code) |
| `bot/Dockerfile` | bot tests, bot image and the API tests (`test_deployment_pins` reads every Dockerfile) |
| `bot/` (tests, requirements...) | bot tests, bot image |
| `.env.template`, `docker-compose.dev.yml` | API tests |
| `ruff.toml` | API and bot tests (their jobs run the Python lint) |
| `docker-compose.yml` | API tests and MariaDB tests (it pins the version they run on) |
| anything else (`.github/workflows/`, `.github/scripts/`, a new top-level path...) | **everything** |

Three safeguards keep this honest. The default is to run everything: only the paths listed as inert run nothing, so a new directory or file is never silently skipped. The script is read from the base branch, so a PR cannot change the rules that judge it (changing the script is itself a change that runs everything). And `api/tests/test_ci_scope.py` pins the table above and fails if an API test starts reading a directory the script does not know about. When you add a test that reads files outside its own directory, add that path to `RULES` in `ci_scope.py` and to the table.

### Nothing is run twice

A check is worth running once per state of the code, so each one has one place:

- **Pull request:** only what its files can affect (table above), plus the PR title. The branch must be up to date with `main` and the merge is a rebase, so the tree that passed here is exactly the one that lands on `main` (the commits get new hashes, the final tree is the same). That is why **`main` has no run of its own after a merge**: it would repeat the same checks on the same files.
- **Tag `vX.Y.Z`** (`release.yml`): the one run of everything, whatever the PRs behind it touched. It is the gate for a release, and for stable tags it is also the trigger: once the checks pass, the same run deploys the tag to `prod` through `deploy.yml`, which refuses a tag that is not on `main`. A manual `prod` deploy of a tag still requires that its run passed on the commit the tag points to (if the run is older than GitHub keeps logs, 90 days, run **Release images** by hand on the tag again). The `dev` deploy needs no check of its own: `main` only receives PRs whose `CI` was green.
- **Weekly:** the moving MariaDB tags, as an early warning that gates nothing.
- **Inside the MariaDB tests**, a guarantee has one test. `test_mariadb_migration_chain.py` covers, for every migration, that it applies on data, that it converges when run again, that it can be undone, that both roads end in the same schema and that the schema matches the models; `test_mariadb_migrations.py` keeps what the chain does not (the rules the database enforces and an older revision with data taken to the head). Do not add a test that proves again what one of those already proves.

What the minimum is, if the minutes of Actions ever become a limit, and what is still repeated, is in [roadmap.md](roadmap.md#ci-cost).

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

Settings → Rules → Rulesets → **release tags** (target: tags, pattern `refs/tags/v*`): creation, update, deletion and force pushes of `v*` tags blocked, with the **Admin** repository role as the only bypass. Without it anyone with write access could tag any branch and start a release (the prod deploy also checks that the tagged commit is on `main` and that its release checks passed, but a rule on the tags keeps that from being the only guard). Tags are immutable once created; an admin can still delete one.

When a second person joins: give them the **Write** role (they can branch, open PRs and merge their own once `CI` is green) and raise the approvals of the `main` ruleset to 1, with "Require approval of the most recent reviewable push", so nobody merges their own PR. Do not raise it before: with no bypass and a single maintainer, nobody could approve the PR. Anyone with write access can also start the **Deploy** workflow and, with a PR that edits a workflow, reach the repository secrets of the SSH deploy keys (each key can only run its deploy script on the server): give Write only to people you would trust with a deploy.
- Do not allow bypassing (applies to admins too).

Settings → General → Pull Requests:

- Allow **rebase merging** only (trial; squash was the previous setting). Merge commits and squash stay disabled.
- Automatically delete head branches.
