# Git workflow

Simplified trunk-based development for a team of 2-3. `main` is the trunk: always green and releasable.

## Rules

1. **Nobody pushes to `main`.** Every change goes through a pull request (branch protection enforces it, also for admins).
2. **Short-lived branches** off `main`, named `<type>/<short-description>` (`feat/ranking-filters`, `fix/timer-stop`, `docs/workflow`). Aim to merge within a day or two; if a feature is bigger, split it into steps that are each safe to merge (behind a setting or not yet reachable from the UI).
3. **Small PRs.** One concern per PR; do not mix refactors with behaviour changes.
4. **The PR title is the commit.** PRs are **squash-merged**, so the title must follow Conventional Commits (`feat(front): ...`, types in `AGENTS.md`); CI checks it. Commits inside the branch can be messy.
5. **Merge when**: the `CI` check is green, one teammate approved, and the branch is up to date with `main`. Delete the branch after merging (GitHub does it automatically).
6. **Review turnaround**: aim to review within a working day. With 2 people the reviewer is simply the other one; do not self-approve.
7. **Releases** are tags `vX.Y.Z` cut from `main` (see [deployment.md](deployment.md#cicd)). There is no `develop` and no release branch; a hotfix is a normal PR to `main` followed by a new tag.

## What CI checks

`.github/workflows/ci.yml` runs on every PR and again on `main` after the merge. The required status is the single job **`CI`**, which passes only if all of these pass (they live in `checks.yml`, the same ones that gate a release):

- API tests (Python 3.13), including the Alembic history guards, the endpoint security list and the `.env.template` check.
- Bot tests (Python 3.11).
- Front tests and ESLint.
- The three Docker images build and contain no secrets, data or baked-in credentials.
- The PR title follows Conventional Commits.

Run the same locally before pushing: see [development.md](development.md#tests-and-lint).

## One-time repository setup (GitHub settings)

Settings → Rules → Rulesets (or Branches → Branch protection rule) for `main`:

- Require a pull request before merging, with **1 approval**; dismiss stale approvals on new pushes.
- Require status checks to pass: select **`CI`**; require the branch to be up to date.
- Block force pushes and deletion.
- Do not allow bypassing (applies to admins too).

Settings → General → Pull Requests:

- Allow **squash merging** only, default message "Pull request title".
- Automatically delete head branches.
