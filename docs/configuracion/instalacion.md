# Instalación

## 1. Descarga el proyecto

```bash
git clone https://github.com/la-viciacion/la-viciacion.git
cd la-viciacion
```

## 2. Crea tu `.env`

Copia la plantilla y rellénala:

```bash
cp .env.template .env
```

Lo mínimo para arrancar (las demás variables tienen valores por defecto razonables, ver [Variables del .env](variables.md)):

| Variable | Qué poner |
|---|---|
| `MARIADB_ROOT_PASSWORD`, `MARIADB_PASSWORD` | Contraseñas largas y distintas para la base de datos. |
| `GOD_ADMIN_PASS` | Contraseña de la cuenta de emergencia `admin`. Larga y única. |
| `SECRET_KEY` | Al menos 32 bytes aleatorios: `openssl rand -hex 32`. |
| `CORS_ORIGINS` | La dirección pública de la app, en una lista JSON: `["https://lavi.ejemplo.com"]`. |

!!! warning "Nunca subas el `.env` a ningún repositorio"
    Contiene todas las claves. Está en el `.gitignore` y no debe salir del servidor.

!!! warning "En Windows con Docker Desktop"
    Añade `DB_DATA=laviciacion_db_data` a tu `.env` **antes del primer arranque**. Así la base de datos vive en un volumen de Docker. Con la carpeta por defecto (`./db/data`), MariaDB 12 no puede reconstruir tablas en Docker Desktop y las migraciones fallan. En Linux no hace falta.

## 3. Arranca

```bash
docker compose up -d --build
```

Es todo. MariaDB empieza con la base de datos vacía y la API construye el esquema completo en su primer arranque (las migraciones se ejecutan solas en cada inicio). También crea el usuario `admin`, los logros y una lista de plataformas. La primera vez puede tardar un par de minutos.

Comprueba que va bien:

```bash
docker compose ps
docker compose logs --tail=50 laviciacion-api
```

El bot de Telegram **no podrá conectarse** (el contenedor se reiniciará en bucle) hasta que le des el token y el grupo (ver [Telegram](telegram.md)); es normal. La API y la app funcionan sin él.

## 4. Entra y crea a los jugadores

1. Abre `http://localhost:3000` (o la dirección de tu servidor).
2. Entra con el usuario **`admin`** y la contraseña de `GOD_ADMIN_PASS`.
3. Ve a **Panel de administración → Jugadores → Usuarios → Nuevo usuario** y crea las cuentas del grupo (ver [Cuentas y acceso](cuentas.md)).

![Pantalla de inicio del panel de administración](../assets/screens/admin-home.webp){ .screenshot }

La cuenta `admin` es de **emergencia**: no es un jugador, nunca aparece en rankings, estadísticas ni avisos. Conviene crear una cuenta de administrador normal para el día a día y dejar `admin` guardada.

!!! tip "Lo que te va a decir el panel"
    En **Inicio**, el bloque **Integraciones** te muestra qué falta por configurar (Telegram, IA, correo…). Nada de eso impide usar la app: sin ello simplemente no se envían avisos ni se busca en RAWG.

## Siguientes pasos

- Conectar [Telegram](telegram.md) y los [servicios externos](servicios.md).
- Poner [HTTPS](operacion.md) si el grupo va a entrar desde fuera de casa.
- Hacer tu primera [copia de seguridad](operacion.md).
