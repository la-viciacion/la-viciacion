# La Viciación: documentation

For people who run it:

- [Deployment](deployment.md): installing, updating, backups, rollback, MariaDB version, CI/CD.
- [Configuration](configuration.md): `.env`, accounts and login, password recovery, API docs.
- [Features](features.md): how the app behaves (seasons, notifications and scheduled jobs, push, platforms, achievements, manual sessions, recommendations, AI notices).

For people who change the code:

- [Architecture](architecture.md): services, layers, data model, domain rules, auth, scheduler.
- [Development](development.md): setup, commands, tests, migrations, debugging.
- [Conventions and recipes](conventions.md): code conventions, best practices, how to implement common changes, definition of done.
- [Migrations](migrations.md): **Alembic rules and verification checklist; mandatory for schema changes.**
- [Git workflow](workflow.md): trunk-based flow, PRs, required CI checks.
- [Roadmap](roadmap.md): pending decisions and known debt.

LLM/agent entry point: [AGENTS.md](../AGENTS.md) (`CLAUDE.md` and `.github/copilot-instructions.md` point to it). Project presentation: [README](../README.md).
