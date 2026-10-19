# Configuración

Esta sección es para quien **monta y administra** La Viciación: instalarla, configurarla, crear las cuentas del grupo, conectar Telegram y mantenerla al día. Si solo quieres usarla, tienes la [guía de usuario](../guia-usuario/index.md).

## Cómo está montada

Son cuatro servicios en un único `docker-compose.yml`:

| Servicio | Qué hace |
|---|---|
| `laviciacion-front` | La app web (una PWA servida por nginx). También reenvía `/api` a la API. Puerto `3000`. |
| `laviciacion-api` | El corazón: guarda los datos, aplica las reglas y ejecuta los avisos programados. |
| `laviciacion-bot` | El bot de Telegram. Solo lee datos de la API (salvo `/activate`). |
| `laviciacion-db` | La base de datos MariaDB, donde vive todo. |

Todo se configura con **un único fichero**, el `.env`, que leen la API, el bot y la base de datos. Lo demás (avisos, IA, plantillas…) se ajusta desde el [panel de administración](panel-admin.md).

## Qué necesitas

- Un servidor (o tu ordenador) con **Docker** y **Docker Compose**.
- Para que el grupo entre desde fuera: un dominio y un proxy inverso con **HTTPS** (las notificaciones del móvil lo exigen). Ver [Operación](operacion.md).
- Opcional, según lo que quieras activar:
    - Un **bot de Telegram** y un grupo → [Telegram](telegram.md).
    - Una clave de **RAWG** para buscar juegos y portadas, y una de **IA** para avisos más graciosos → [Servicios externos](servicios.md).
    - Un servidor **SMTP** para recuperar contraseñas por correo → [Cuentas y acceso](cuentas.md).

## Por dónde empezar

<div class="grid cards" markdown>

- :material-download: **[Instalación](instalacion.md)**

    De cero a la app funcionando en unos minutos.

- :material-file-cog: **[Variables del .env](variables.md)**

    Qué hace cada variable.

- :material-account-key: **[Cuentas y acceso](cuentas.md)**

    Crear jugadores, contraseñas y recuperación por correo.

- :material-send: **[Telegram](telegram.md)**

    Crear el bot y conectarlo al grupo.

- :material-puzzle: **[Servicios externos](servicios.md)**

    RAWG, IA, notificaciones push y el tiempo.

- :material-view-dashboard: **[Panel de administración](panel-admin.md)**

    Un recorrido por todo lo que se hace desde el panel.

- :material-wrench: **[Operación](operacion.md)**

    Actualizar, copias de seguridad, HTTPS y vuelta atrás.

</div>

!!! info "¿Buscas el detalle técnico?"
    El funcionamiento interno, las migraciones y el despliegue con GitHub Actions están en la [documentación técnica](../desarrollo/index.md) (en inglés).
