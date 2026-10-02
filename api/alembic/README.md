# Alembic Database Migrations

> **Read [docs/migrations.md](../../docs/migrations.md) first.** It holds the mandatory rules (immutability, linear history, naming, idempotency, verification checklist). The commands below are only a quick reference; where they differ, that page wins.

This directory contains database migration scripts for La Viciación API.

## Quick Start

### Create a new migration (auto-generate)
```bash
alembic revision --autogenerate -m "description of changes"
```

### Create a new empty migration
```bash
alembic revision -m "description of changes"
```

### Apply migrations
```bash
# Upgrade to the latest version
alembic upgrade head

# Upgrade by one version
alembic upgrade +1

# Upgrade to a specific revision
alembic upgrade <revision_id>
```

### Rollback migrations
```bash
# Downgrade by one version
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade <revision_id>

# Downgrade all the way
alembic downgrade base
```

### View migration history
```bash
# Show current revision
alembic current

# Show migration history
alembic history

# Show verbose history
alembic history --verbose
```

## Best Practices

1. **Always review auto-generated migrations** - Alembic's autogenerate is smart but not perfect
2. **Test migrations in development first** - Never run untested migrations in production
3. **Write both upgrade and downgrade** - Always implement the downgrade path
4. **One logical change per migration** - Keep migrations focused and atomic
5. **Add meaningful messages** - Use descriptive migration messages

## Configuration

- **alembic.ini**: Main configuration file
- **env.py**: Environment configuration that loads your models and database connection
- **versions/**: Directory containing all migration scripts

## Environment Variables

Migrations use the same environment variables as the main application:
- `MARIADB_HOST`
- `MARIADB_DATABASE`
- `MARIADB_USER`
- `MARIADB_PASSWORD`

These come from the Docker environment (`env_file: .env`), or from the root `.env` when running locally.
