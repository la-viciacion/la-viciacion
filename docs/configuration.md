# Configuration

Everything an operator sets up: the environment file, accounts and login, password recovery and the API docs. What the app does with its data (seasons, notifications, sessions, achievements, AI) is in [features.md](features.md); how to run and update it is in [deployment.md](deployment.md).

## Environment

Copy `.env.template` to `.env` and fill in your values. That single file is read by every service (`api`, `bot` and `db`) through `env_file` in `docker-compose.yml`; when running the api or bot outside Docker they fall back to that same `.env`. Variables already present in the environment always win over the file.

`docker-compose.yml` and the `Dockerfile`s are ready to use as they are; they contain no secrets. The images hold no configuration either: everything arrives at run time through `.env` (see [deployment.md](deployment.md#images)).

## Users and login

- Accounts are created by an admin in the panel (Usuarios, "Nuevo usuario"); there is no public sign-up. The admin sets the initial password and shares it with the user, who can change it from their profile.
- The **email** is the login identifier (unique, stored lower-case). The **username** is the user's unique nickname (no `@`, no spaces). At login either one is accepted.
- On every start the API creates/restores the emergency admin `admin` ("Admin") with `GOD_ADMIN_PASS`.
- Login is limited to 5 failed attempts per account and, when the real client address is known (see `FORWARDED_ALLOW_IPS` in `.env.template`), 40 per client every 15 minutes (then HTTP 429 until the window passes). Counters live in memory, so a restart clears them. A disabled account gets a 403 after a correct password.
- Changing or resetting a password (by the user or by an admin) logs that account out everywhere: the token carries a fingerprint of the password hash. Deploying the version that introduced it also closes every existing session once.
- The session lasts `ACCESS_TOKEN_EXPIRE_MINUTES` minutes from login (10080 = 7 days) and is not renewed.

## Password recovery

The login page has **¿Has olvidado tu contraseña?**: the user types their email or username and gets an email with a one-time link (valid 1 hour) to choose a new password. It needs an SMTP server; without one the API answers that recovery is not configured, and an admin can always set a password from the panel (Usuarios → Editar).

Set in `.env` (see `.env.template`): `PUBLIC_URL` (where users reach the app, the link points there), `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`starttls` on 587, the default, or `ssl` on 465), `SMTP_EMAIL` (the From address), `SMTP_USER`/`SMTP_PASS` (login, if the server asks for it; `SMTP_USER` defaults to `SMTP_EMAIL`). The answer never says whether an account exists, the link is only usable once, and using it signs out every session of that user. Accounts without an email (for instance `admin`) cannot use it: the `admin` password is `GOD_ADMIN_PASS`.

To check the setup, the **Sistema** page of the admin panel (**Correo** card): it shows whether mail is configured (or which variables are missing, and the server and sender in use, never the password) and a button that sends a test email to the email of the admin who presses it (`POST /manage/settings/test-email`). If the server refuses it, the panel shows why.

## API docs

Swagger/ReDoc/`openapi.json` are disabled by default because they publish every endpoint. For local development set `API_DOCS_ENABLED=true` in `.env` and open `/api/v1/docs`.
