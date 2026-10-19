# Contributing

1. Set up the project: [docs/desarrollo/development.md](docs/desarrollo/development.md).
2. Read [docs/desarrollo/conventions.md](docs/desarrollo/conventions.md) (code conventions and recipes) and, for anything that touches the database schema, [docs/desarrollo/migrations.md](docs/desarrollo/migrations.md) first.
3. Branch off `main` as `<type>/<short-description>`, keep the change small and focused, and add or update tests for the logic you touch.
4. Run the checks before pushing: API tests, front tests and lint (commands in [docs/desarrollo/development.md](docs/desarrollo/development.md#tests-and-lint)).
5. Open a pull request. It is rebase-merged: each commit lands on `main` as is, so commits and the PR title must follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`). The `CI` check must be green. Details: [docs/desarrollo/workflow.md](docs/desarrollo/workflow.md).

Update the docs in the same pull request when you change behaviour, configuration or operations. Never commit secrets, `.env` or database dumps.
