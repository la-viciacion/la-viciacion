# Variables del .env

Un único `.env` en la raíz del proyecto lo leen la API, el bot y la base de datos (`env_file` en `docker-compose.yml`). La plantilla comentada es `.env.template`. Si cambias algo, recrea los contenedores: `docker compose up -d`.

!!! info "Las claves de servicios externos solo viven aquí"
    `TELEGRAM_TOKEN`, `TELEGRAM_GROUP_ID`, `TELEGRAM_ADMIN_CHAT_ID`, `OPENAI_AI_API_KEY`, `GOOGLE_AI_API_KEY`, `ANTHROPIC_AI_API_KEY`, `OPENAI_ADMIN_KEY`, `RAWG_API_KEY`, `TWITCH_CLIENT_SECRET` y las credenciales SMTP **nunca se guardan en la base de datos**, ni cifradas. Así, una copia de seguridad no sirve para manejar el bot del grupo ni gastar la cuota de la IA. El panel solo te dice si cada una está puesta o no, sin enseñarla.

## Obligatorias

| Variable | Para qué sirve |
|---|---|
| `MARIADB_HOST` | Dónde está la base de datos. Con Docker, `laviciacion-db`. |
| `MARIADB_ROOT_PASSWORD` | Contraseña del administrador de MariaDB. |
| `MARIADB_DATABASE`, `MARIADB_USER`, `MARIADB_PASSWORD` | Base de datos, usuario y contraseña que usa la API. |
| `GOD_ADMIN_PASS` | Contraseña de la cuenta de emergencia `admin`, que se crea o restaura en cada arranque. |
| `SECRET_KEY` | Firma las sesiones. Mínimo 32 bytes aleatorios (`openssl rand -hex 32`). Cambiarla cierra todas las sesiones. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración de la sesión (10080 = 7 días). La app la renueva a mitad de vida. |
| `CORS_ORIGINS` | Lista JSON de orígenes permitidos: la dirección pública de la app. |
| `API_URL` | Cómo llega el bot a la API: `http://laviciacion-api:5000/api/v1`. |
| `ENVIRONMENT` | Etiqueta del entorno (`development`, `production`). |
| `SENTRY_URL_API`, `SENTRY_URL_BOT` | DSN de Sentry. Déjalas **vacías** para desactivarlo, pero la línea debe existir. |
| `API_LOG_LEVEL`, `BOT_LOG_LEVEL` | `INFO` o `DEBUG`. |

## Opcionales

### Telegram

| Variable | Para qué sirve |
|---|---|
| `TELEGRAM_TOKEN` | Token del bot (de @BotFather). El bot no arranca sin él. |
| `TELEGRAM_GROUP_ID` | Identificador del grupo. El bot tampoco arranca sin él. |
| `TELEGRAM_ADMIN_CHAT_ID` | Tu chat privado, para los avisos a administradores (errores, ejecuciones lentas). |

Detalle en [Telegram](telegram.md).

### Servicios externos

| Variable | Para qué sirve |
|---|---|
| `RAWG_API_KEY` | Opcional. El respaldo de IGDB para buscar juegos y completar la ficha. Sin ella (y sin IGDB), buscar juegos no encuentra nada. |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | Opcionales. Una aplicación de Twitch, para que [IGDB](servicios.md#igdb-la-fuente-principal-de-los-juegos), la fuente principal, busque y describa los juegos. Sin ellas se usa solo RAWG. |
| `OPENAI_AI_API_KEY`, `OPENAI_AI_MODEL` | La clave de OpenAI y el modelo que se usa por defecto con ella (por ejemplo `gpt-4.1-mini`). El código no trae ningún modelo. |
| `GOOGLE_AI_API_KEY`, `GOOGLE_AI_MODEL` | Lo mismo para Google (Gemini), por ejemplo `gemini-3.5-flash-lite`. |
| `ANTHROPIC_AI_API_KEY`, `ANTHROPIC_AI_MODEL` | Lo mismo para Anthropic (Claude), por ejemplo `claude-haiku-5-5`. La guía de juego busca en la web: con Claude, la organización de Anthropic tiene que tener activada la búsqueda web. |
| `HETZNER_API_TOKEN` | Opcional. Un token de **solo lectura** de Hetzner Cloud, para la página **Servidor**. Sin él, la página dice que no está configurada. |
| `PROMETHEUS_URL` | Opcional. La dirección de Prometheus, para que la página **Servidor** añada memoria, espacio en disco, carga y tiempo encendido. Con `COMPOSE_PROFILES=monitoring` la API ya la recibe sola (`http://laviciacion-prometheus:9090`), así que solo hace falta para un Prometheus que esté en otro sitio. Sin Prometheus, la página enseña solo lo que da Hetzner. |
| `HETZNER_SERVER_ID` | Opcional. El número del servidor en Hetzner; vacío = el único servidor del proyecto. |
| `OPENAI_ADMIN_KEY` | Opcional. Una clave de **administración** de OpenAI, solo para leer cuánto se ha gastado (**IA → Uso y coste**). No escribe avisos. |

No hay ninguna variable que diga qué proveedor usar: es el que tenga clave y, con los dos, el que se elige en el panel (**IA → Avisos con IA**), donde también se puede cambiar el modelo con la lista que da el proveedor. Sin la clave y el modelo de al menos un proveedor, la IA no escribe nada y los avisos salen como texto normal. Ver [Servicios externos](servicios.md).

El chat de la app usa el mismo proveedor y la misma clave. Solo tiene una variable propia por proveedor, **opcional**:

| Variable | Para qué sirve |
|---|---|
| `OPENAI_CHAT_AI_MODEL`, `GOOGLE_CHAT_AI_MODEL`, `ANTHROPIC_CHAT_AI_MODEL` | El modelo que usa el chat con ese proveedor. Si no la pones, usa el modelo de los avisos (`OPENAI_AI_MODEL`, `GOOGLE_AI_MODEL`, `ANTHROPIC_AI_MODEL`). |

Ver [Servicios externos](servicios.md#chat-de-la-app).
### Correo (recuperar contraseña)

| Variable | Para qué sirve |
|---|---|
| `PUBLIC_URL` | Dirección pública de la app; el enlace del correo apunta ahí. |
| `SMTP_HOST`, `SMTP_PORT` | Servidor de correo saliente y su puerto (587 por defecto). |
| `SMTP_SECURITY` | `starttls` (puerto 587, por defecto) o `ssl` (465). `none` solo para pruebas locales. |
| `SMTP_EMAIL` | Dirección que figura como remitente. También es el contacto ante los servicios push. |
| `SMTP_USER`, `SMTP_PASS` | Credenciales, si el servidor las pide. `SMTP_USER` vale `SMTP_EMAIL` si lo dejas vacío. |

### Ejecución y puertos

| Variable | Para qué sirve |
|---|---|
| `TZ` | Zona horaria (por defecto `Europe/Madrid`). **Importante:** la temporada cambia a medianoche de esta zona y también fija las horas de los avisos programados y los logros del tiempo. |
| `API_DOCS_ENABLED` | `true` publica la documentación interactiva de la API en `/api/v1/docs`. Déjalo en `false` en producción. |
| `FRONT_HOST_IP` / `FRONT_HOST_PORT` | Dirección y puerto con los que se publica la app (por defecto `0.0.0.0:3000`). |
| `API_HOST_IP` / `API_HOST_PORT` | Lo mismo para la API (por defecto `127.0.0.1:5000`). |
| `DB_HOST_IP` / `DB_HOST_PORT` | Lo mismo para la base de datos (por defecto `127.0.0.1:3307`). |
| `LAVI_SUBNET` | Rango de la red de Docker que comparten los contenedores (por defecto `192.168.64.0/20`). Está fijo para que `FORWARDED_ALLOW_IPS` pueda nombrarlo. Dos entornos en el mismo servidor (producción y desarrollo) necesitan rangos distintos. Docker solo lo lee al crear la red, no en un redespliegue normal. |
| `FORWARDED_ALLOW_IPS` | Proxies en los que confía la API para saber la IP real del cliente: direcciones o redes separadas por comas. Detrás del nginx del front, pon el rango entero de `LAVI_SUBNET`. Sin esto, ni el registro de auditoría ni el límite de intentos de acceso por IP ven al cliente real. Nunca `*`. |
| `DB_DATA` | Dónde guarda MariaDB sus ficheros. Vacío: carpeta `./db/data` (Linux). `laviciacion_db_data`: un volumen de Docker (**Windows**). |
| `LAVI_VERSION` | Versión de las imágenes publicadas que se descargan (por defecto `latest`). |

!!! danger "No publiques la API ni la base de datos"
    Por defecto solo escuchan en `127.0.0.1`. Deja la app (`:3000`) detrás de un proxy con HTTPS y no abras los otros puertos a internet.
