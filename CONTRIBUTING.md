# Contributing

1. Set up the project: [docs/development.md](docs/development.md).
2. Read [docs/conventions.md](docs/conventions.md) (code conventions and recipes) and, for anything that touches the database schema, [docs/migrations.md](docs/migrations.md) first.
3. Branch off `main` as `<type>/<short-description>`, keep the change small and focused, and add or update tests for the logic you touch.
4. Run the checks before pushing: API tests, front tests and lint (commands in [docs/development.md](docs/development.md#tests-and-lint)).
5. Open a pull request. Its title becomes the squash commit and must follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `style:`, `test:`, `chore:`). The `CI` check must be green. Details: [docs/workflow.md](docs/workflow.md).

Update the docs in the same pull request when you change behaviour, configuration or operations. Never commit secrets, `.env` or database dumps.
