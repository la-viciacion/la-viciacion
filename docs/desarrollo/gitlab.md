# Moving to GitLab (prepared, not in use)

The repository is on GitHub and stays there. These files exist so that, if the code has to be private and GitHub Free stops being enough (branch protection, rulesets, auto-merge and environments are not available in private repositories on the Free plan), a move to GitLab is a push plus the settings below, not a rewrite. **Nothing here runs on GitHub**, and nothing on GitHub was removed. They were written without a GitLab project to try them on: see [what was not tried](#what-was-not-tried).

## What maps to what

| GitHub | GitLab | Notes |
|---|---|---|
| `.github/workflows/ci.yml` | `.gitlab-ci.yml` (`pr-title`, `changes`, `checks`) | Only merge requests and tags run pipelines; a plain push does not, as on GitHub |
| `.github/workflows/checks.yml` | `.gitlab/ci/checks.yml` | A child pipeline generated per merge request by `.gitlab/scripts/ci-scope.sh` |
| `.github/scripts/ci_scope.py` | the same file | Reused as it is, read from the merge base; the day GitHub is left, move it and update `api/tests/test_ci_scope.py` |
| `mariadb-tests.yml`, `mariadb-versions.yml` | `.gitlab/ci/mariadb.yml`, job `mariadb-versions` | The weekly run needs a pipeline schedule |
| `release.yml` | `release-checks`, `publish` | Images go to the project's registry (`registry.gitlab.com/<group>/<project>/laviciacion-<service>`), so the `image:` names in `docker-compose.yml` would change |
| `deploy.yml` | `.gitlab/ci/deploy.yml` | Build > Pipelines > Run pipeline, on `main`, picking `DEPLOY_TARGET` and `DEPLOY_VERSION` |
| `dependabot.yml` | `renovate.json5`, `.gitlab/ci/renovate.yml` | GitLab has no Dependabot; Renovate runs as a scheduled job |
| `pull_request_template.md` | `.gitlab/merge_request_templates/Default.md` | |
| branch ruleset + required `CI` check | project settings, below | |

## Project settings

- **Merge requests** (Settings > Merge requests): merge method **Fast-forward merge**, **squash: Require** (the MR title is the commit message, as now), **Pipelines must succeed**, **All threads must be resolved** (optional), delete the source branch on merge. Fast-forward is what "the branch must be up to date with `main`" means here: what the MR tested is exactly what lands on `main`.
- **Protected branch `main`** (Settings > Repository): allowed to push and merge: **Maintainers** for merge, **No one** for push. Force push off.
- **Protected tags** `v*`: only Maintainers can create them (the tag is what the prod deploy builds).
- **Approvals**: required approvals are a paid feature on GitLab.com; with a single maintainer there are none anyway. The note in [workflow.md](workflow.md) about raising approvals when a second person joins would need Premium, or a convention.
- **Pipeline schedules** (Build > Pipeline schedules), both on `main`:
  - weekly, variable `SCHEDULE_JOB=mariadb-versions`;
  - daily or weekly, variable `SCHEDULE_JOB=renovate`.

## CI/CD variables (Settings > CI/CD > Variables)

Mark everything secret as **Protected** (only pipelines on `main` and protected tags can read it; this also closes the hole that on GitHub lets a PR that edits a workflow reach the repository secrets) and **Masked** where the value allows.

| Variable | Type | Purpose |
|---|---|---|
| `DEPLOY_SSH_KEY_DEV`, `DEPLOY_SSH_KEY_PROD` | **File**, Protected | The private keys (the value must end with a newline) |
| `DEPLOY_HOST`, `DEPLOY_USER` | Variable, Protected | Shared by both targets |
| `DEPLOY_KNOWN_HOSTS` | Variable, Protected | `<host> ssh-ed25519 AAAA...`, read from the server |
| `DEPLOY_URL_DEV`, `DEPLOY_URL_PROD` | Variable | Base URL of each environment, for the keepalive check |
| `NOTIFY_TELEGRAM_TOKEN`, `NOTIFY_TELEGRAM_CHAT_ID` | Variable, Protected, Masked | The CI bot and chat (not the app's bot) |
| `GITLAB_READ_TOKEN` | Variable, Protected, Masked | Project access token, scope `read_api`; only if the job token cannot list pipelines (see below) |
| `RENOVATE_TOKEN` | Variable, Masked | Project access token, role Developer, scopes `api` and `write_repository` |
| `PUBLISH_IMAGES` | Variable | `true` to publish images on a tag (off for now, as on GitHub) |

## Differences from GitHub that matter

- **Environments with required reviewers** (the prod approval) are a Premium feature on GitLab too, so `deploy-prod` has no approval step. The same compensations apply: `main` only, tag must have passed, protected variables.
- **Minutes**: GitLab.com Free gives about 400 compute minutes a month on its shared runners. Registering a runner on the server (Settings > CI/CD > Runners) removes that limit; docker-in-docker jobs need a runner with privileged mode.
- **No cache between builds of the images** (`cache-from: type=gha` has no counterpart here); the builds are slower than on GitHub.
- **The `ci` job of GitHub** (the single required status) has no equivalent because it is not needed: *Pipelines must succeed* looks at the whole pipeline.
- Changes under `.gitlab/`, `.gitlab-ci.yml` and `renovate.json5` are unclassified for `ci_scope.py`, so on GitHub they run every check.

## What was not tried

Written from the documentation, never run. Check these first when a project exists:

1. `MARIADB_IMAGE` coming from the `mariadb-image` job's dotenv report into `services: - name:` of `api-mariadb`. If it is not expanded there, set the image statically in `.gitlab/ci/checks.yml` and keep `mariadb-pin.sh` as a check that it matches `docker-compose.yml`.
2. `verify-release.sh` reading the project's pipelines with `CI_JOB_TOKEN`. If it answers 401/403, create `GITLAB_READ_TOKEN`.
3. The child pipeline made from `child.yml` (an artifact) and `strategy: depend` turning the parent red when the child fails.
4. The `notify` job reading `deploy-result.env` of a failed `deploy-*` job through `needs` with `artifacts: true`.
5. Docker-in-docker (`docker:27-dind`) on the shared runners.
6. `renovate.json5`: the weekday schedules and the grouping; pin `renovate/renovate` in `.gitlab/ci/renovate.yml`.

Lint the CI files in the project (CI/CD > Editor > Validate, or *Pipeline editor*) before relying on them.
