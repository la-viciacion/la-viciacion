# La Viciación

<p align="center"><img src="design/laViciacionLogo.jpg" alt="La Viciación" width="220"></p>

A private app for a group of friends to keep track of the time they spend playing video games, and to enjoy comparing it.

Start a timer when you sit down to play, or add a session by hand afterwards. Everything else is computed from those sessions: your library per season, the rankings of the group, streaks, achievements, recommendations. A Telegram bot and push notifications keep the group posted.

## What it does

- **Timers and manual sessions**: play with a running timer or log a finished session; correct or delete your own.
- **Library per season**: a season is a calendar year, so every January starts from zero while the history stays. Mark games as completed.
- **Rankings and streaks**: who played more hours or more games, per season or overall, and who has the longest streak.
- **Achievements**: unlocked automatically (early riser, nocturnal, teamwork, completed games...) and announced to the group.
- **Recommendations**: games other players have that you never tried, weighted by what you like to play.
- **Telegram bot** for the group: your stats, rankings and recommendations on demand, and the notices and weekly summaries sent to the group. **Push notifications** on the installed PWA, including a pinned notification while a timer runs.
- **Notices written by an AI** (optional, Google Gemini or OpenAI) to make announcements funnier.
- **Admin panel** for accounts, games, platforms, achievements, notifications and system settings. There is no public sign-up: admins create the accounts.

The interface and the messages are in Spanish; the code and the documentation are in English.

## How it is built

Four services in one `docker-compose.yml`:

| Service | Stack |
|---|---|
| `api` | Python 3.14, FastAPI, SQLAlchemy 2, Alembic. Source of truth: REST API, business rules and the scheduler |
| `front` | Vanilla JS (ES modules), no framework and no build step, served by nginx as an installable PWA |
| `bot` | Python, python-telegram-bot; a read-only client of the API |
| `db` | MariaDB 12.3 LTS |

Totals, rankings and streaks are never stored: they are computed from the sessions when requested. More in [docs/architecture.md](docs/architecture.md).

## Quick start

You need Docker with Compose.

```bash
cp .env.template .env      # fill in the passwords and keys (see docs/configuration.md)
docker compose up -d --build
```

Then open http://localhost:3000 and log in as `admin` with the `GOD_ADMIN_PASS` you set. Create the players from the admin panel. On Windows, set `DB_DATA=laviciacion_db_data` in `.env` first ([why](docs/deployment.md#database-storage-linux-vs-windows)).

A server does not need to build anything: the images are published to GHCR on every release, and `docker compose pull && docker compose up -d` is the whole deploy ([deployment guide](docs/deployment.md)).

## Documentation

Everything lives in [`docs/`](docs/index.md):

| If you want to... | Read |
|---|---|
| Install, update, back up or roll back | [Deployment](docs/deployment.md) |
| Set up `.env`, logins, password recovery | [Configuration](docs/configuration.md) |
| Know how the app behaves (seasons, notifications, sessions, AI...) | [Features](docs/features.md) |
| Understand the code and the data model | [Architecture](docs/architecture.md) |
| Run it locally, run the tests | [Development](docs/development.md) |
| Change the code | [Conventions and recipes](docs/conventions.md), [Migrations](docs/migrations.md), [Git workflow](docs/workflow.md) |

Working on this repository with an AI assistant? Point it to [AGENTS.md](AGENTS.md).

## Contributing

Short-lived branches and pull requests squash-merged into `main`, with the `CI` check green. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[GNU AGPL v3](LICENSE).
