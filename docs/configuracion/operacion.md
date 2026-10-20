# Operación

Mantener La Viciación en marcha: actualizar, hacer copias, ponerla detrás de HTTPS y volver atrás si algo sale mal.

## Actualizar

```bash
git pull                                  # el compose y la documentación
docker compose up -d --build              # reconstruye y recrea lo que cambió
docker compose logs --tail=100 laviciacion-api   # busca «Running upgrade …» y ningún error
```

Cuando se publiquen imágenes en GHCR bastará con `docker compose pull && docker compose up -d` (y `LAVI_VERSION` en el `.env` fija una versión concreta).

Las **migraciones de la base de datos se aplican solas** al arrancar la API, así que actualizar es un solo paso. Eso tiene dos consecuencias:

!!! warning "Haz una copia antes de actualizar"
    Si la nueva versión incluye una migración, la copia de seguridad es el único camino de vuelta. Si la API se reinicia en bucle tras actualizar, es que la migración está fallando: mira los registros y **no fuerces nada**; consulta las [migraciones](../desarrollo/migrations.md) (en inglés).

- La API es **una sola réplica** (los avisos programados corren dentro). No la escales.

## Copias de seguridad

Dos formas:

=== "Desde el panel"

    **Sistema → Copia de seguridad → Descargar copia (.sql.gz)**. Cómodo para una copia rápida. No incluye rutinas ni eventos (no tiene), y es **tan sensible como la propia base de datos** (hashes de contraseñas, fotos, claves): guárdala fuera del repositorio y no la compartas.

=== "Desde el servidor"

    ```bash
    docker compose exec laviciacion-db sh -c \
      'mariadb-dump -u root -p"$MARIADB_ROOT_PASSWORD" --single-transaction --routines "$MARIADB_DATABASE"' \
      > backup-$(date +%F).sql
    ```

    Es la que debes hacer **antes de un despliegue con migración**.

Los ficheros `*.sql`, `*.sql.gz` y `*.dump` están en el `.gitignore`. Guárdalos en otro sitio.

### Restaurar

En una base de datos nueva y vacía, copia el volcado a `db/init/` (acepta `.sql` y `.sql.gz`) y arranca con la carpeta de datos vacía: MariaDB lo importa en el **primer arranque**. En una base ya en marcha, impórtalo con el cliente `mariadb` normal.

## Volver atrás

- **Código**: pon la versión anterior en `LAVI_VERSION` (o vuelve a la etiqueta anterior del repositorio), y `docker compose up -d`.
- **Datos**: si se aplicó una migración, restaura la copia anterior al despliegue. Solo se hace `alembic downgrade` cuando esa migración define una vuelta real, y para cualquier cosa destructiva se prefiere restaurar.

## HTTPS y exposición

El compose publica la app en el puerto `3000` por HTTP, y la API y la base de datos **solo en `127.0.0.1`**. El HTTPS y el dominio público los pone un **proxy inverso** delante del contenedor `laviciacion-front` (nginx, Caddy, Traefik… no forman parte del proyecto). Necesitas HTTPS para las notificaciones push.

- `FRONT_HOST_IP`/`FRONT_HOST_PORT` cambian dónde se publica la app (por ejemplo, solo en la IP interna del servidor).
- Pon `CORS_ORIGINS` con el origen público y `PUBLIC_URL` con la dirección real.
- Con proxy, pon en `FORWARDED_ALLOW_IPS` el rango de `LAVI_SUBNET` (la red de los contenedores) para que el registro de auditoría y el límite de intentos de acceso por cliente vean la IP real. Si producción y desarrollo comparten servidor, cada uno necesita su propio `LAVI_SUBNET`.
- **No publiques nunca la API ni la base de datos directamente.**

## La base de datos

- **Versión fija**: el compose usa `mariadb:12.3.3`. **No cambies nunca la versión de una base de datos que ya tiene datos editando la imagen**: MariaDB no admite bajar de versión un directorio de datos (uno creado por la 13.0 no se abre con la 12.3). Para cambiar de serie, haz un volcado y empieza con un directorio vacío.
- **Dónde viven los datos**: en `./db/data` por defecto (Linux) o en un volumen de Docker si pones `DB_DATA` (obligatorio en Windows). Con el volumen no verás los ficheros en la carpeta del proyecto: las copias se hacen con `mariadb-dump`.

## Salud y registros

- `GET /api/v1/keepalive` es el endpoint de comprobación ligero. La base de datos y la API tienen healthcheck en el compose, y el bot espera a que la API esté sana.
- `docker compose logs -f laviciacion-api` (o `laviciacion-bot`) para seguirlos. Docker conserva como máximo tres ficheros de 10 MB por contenedor, y los registros propios de la API (`api/logs`) rotan cada día y guardan una semana.
- Con `API_LOG_LEVEL=DEBUG` (y recrear el contenedor) verás más detalle. Sentry se activa si pones su DSN en `SENTRY_URL_API` / `SENTRY_URL_BOT`.

## Zona horaria y cambio de temporada

La temporada es el año de la fecha **del servidor**: mantén `TZ` puesto (por defecto `Europe/Madrid`) para que el año cambie a medianoche hora local, y no a medianoche UTC.

!!! info "Más detalle"
    Despliegue automático con GitHub Actions, imágenes, migraciones y todas las comprobaciones están en la [documentación técnica](../desarrollo/deployment.md) (en inglés).
