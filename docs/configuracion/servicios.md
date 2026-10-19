# Servicios externos

Todos son opcionales: la app arranca sin ninguno. El panel (**Inicio → Integraciones**) te dice cuáles faltan.

## RAWG: buscar juegos y portadas

[RAWG](https://rawg.io/apidocs) es el catálogo del que salen los datos de los juegos (portada, géneros, desarrollador, fecha, etiquetas).

1. Pide una clave gratuita en <https://rawg.io/apidocs>.
2. Ponla en el `.env`: `RAWG_API_KEY=tu_clave`, y `docker compose up -d`.

Sin clave, la búsqueda de juegos nuevos y las sincronizaciones no hacen nada (los juegos se pueden crear a mano, solo con el nombre).

En **Catálogo → Juegos** del panel:

- **Sincronizar con RAWG…** recorre los juegos incompletos para rellenar lo que falte. Pide confirmación, trabaja en segundo plano con una ventana de progreso y se puede cancelar.
- El filtro **Datos de RAWG** (*Incompletos*, *Sin ID de RAWG*) te dice qué juegos queda por arreglar a mano.
- **⋯ → Resincronizar (RAWG y HLTB)…** actualiza **un** juego desde las dos fuentes.

![El catálogo de juegos en el panel](../assets/screens/admin-games.webp){ .screenshot }

### Tiempos de HowLongToBeat

Los tiempos para completar (la historia principal) vienen de [HowLongToBeat](https://howlongtobeat.com), **sin clave**. **Sincronizar tiempos (HLTB)…** reemplaza el tiempo de los juegos que elijas (todos, solo los que no tienen, los que tienen un tiempo increíble o los N jugados más recientemente). Cada juego tarda unos 5 segundos y la ventana lo calcula antes de aceptar. Con esos tiempos se calculan la **deuda** y algunos logros.

## IA: avisos más graciosos

La IA reescribe algunos avisos del grupo (un juego nuevo, un juego completado, cambios en los rankings…) con humor. Sin ella los avisos salen como texto normal.

Necesitas **las tres** variables en el `.env`:

```ini
AI_PROVIDER=google          # o openai
AI_API_KEY=tu_clave
AI_MODEL=gemini-3.5-flash-lite   # un modelo de ese proveedor
```

El código no trae proveedor ni modelo por defecto, y desde el panel no se pueden cambiar (solo se muestran). Lo que sí se edita desde el panel, en **Notificaciones → IA**:

- El **interruptor** de la IA.
- Los **avisos que la usan**, cada uno con su propio interruptor y sus **instrucciones** (prompt) editables. **Restaurar las originales** vuelve a seguir las del código.
- **Probar la IA**, que le pide una frase a la configuración activa y te enseña la respuesta o por qué falló.

![La IA en el panel](../assets/screens/admin-ai.webp){ .screenshot }

## Notificaciones push

Es un segundo canal junto a Telegram, **activado por defecto** y sin nada que configurar: la API crea sus claves VAPID (un par para todo el servidor) en el primer arranque. Solo necesita **HTTPS** delante de la app, y que cada jugador acepte los avisos en cada dispositivo. Si lo necesitas, **Notificaciones → Canales → Avisos en la app (push)** permite cambiar el contacto (por defecto, `SMTP_EMAIL`), apagarlo o regenerar las claves (lo que desuscribe todos los dispositivos).

## Open-Meteo: el tiempo y las ciudades

Los logros que dependen del tiempo (tormenta, niebla) y la búsqueda de la ciudad en el perfil usan [Open-Meteo](https://open-meteo.com), **sin clave ni cuenta**. Solo necesitan que el contenedor de la API pueda salir a internet por HTTPS. Si no responde, la búsqueda de ciudad devuelve un error y esos logros esperan a la siguiente comprobación.
