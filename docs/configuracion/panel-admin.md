# Panel de administración

Los administradores ven en el menú lateral **Administración → Panel de administración**. Cada sección tiene sus pestañas, y cada cambio que haces queda en el [registro](#sistema).

## Inicio

Un resumen de la instalación: cuántos usuarios, juegos, sesiones, timers activos y entradas de biblioteca hay; **Requiere atención** (por ejemplo, jugadores sin Telegram o juegos sin ID de RAWG, con un enlace directo para arreglarlos) y **Integraciones**, que te dice qué servicios faltan por configurar.

![Inicio del panel](../assets/screens/admin-home.webp){ .screenshot }

## Catálogo

### Juegos

La lista de todos los juegos con búsqueda, orden y filtros. **Editar** cambia cualquier dato (nombre, desarrollador, fecha, géneros, etiquetas, portada, tiempo medio…). Aquí están también las sincronizaciones con RAWG y HowLongToBeat: ver [Servicios externos](servicios.md).

### Plataformas

El catálogo de plataformas que se pueden elegir en sesiones y biblioteca. Puedes **añadir** una (su identificador sale del nombre y no cambia nunca), **renombrarla** (todo lo que la usa la sigue) y **borrar** una que nadie use. Si aún tiene sesiones o entradas, te dice cuántas.

![Plataformas](../assets/screens/admin-platforms.webp){ .screenshot }

### Logros

Todos los logros con su estado. Pulsa uno para ver quién lo ha conseguido y cuándo. Por cada logro puedes cambiar:

- **Activo**: apagado, nadie lo gana ni se anuncia, pero lo ya ganado se conserva.
- **Secreto**: oculto para quien no lo tiene.
- **Especial** (nivel 1 plateado, 2 dorado, 3 morado): le da el aura. Los especiales son también secretos.
- **Desde**: la temporada en la que empieza a contar. Los nuevos logros empiezan en 2027.
- El texto y la imagen.

En cada logro de un jugador, **Editar** cambia la fecha en que lo consiguió y **Revocar** lo retira sin avisar. Ojo: si el jugador sigue cumpliendo la condición, se volverá a conceder en la siguiente comprobación; corrige antes el dato que lo provocó.

![Logros en el panel](../assets/screens/admin-achievements.webp){ .screenshot }

**Recalcular logros…** vuelve a calcular todos los logros de todas las temporadas a partir de las sesiones y la biblioteca, **sin avisar a nadie**. Funciona en dos pasos: una vista previa de lo que añadiría, corregiría y revocaría, y, tras escribir `RECALCULAR`, el recálculo en segundo plano. Puedes elegir jugadores, temporadas y logros. Úsalo cuando importes historial o cuando arregles datos antiguos.

## Jugadores

- **Usuarios**: crear, editar y desactivar cuentas (ver [Cuentas y acceso](cuentas.md)).
- **Sesiones**: todas las sesiones de todos, con filtros. Puedes **crear una sesión a mano** (para un timer olvidado, por ejemplo), editar el juego, la plataforma, el inicio o el fin de cualquiera, incluso de temporadas cerradas, y cerrar un timer atascado poniéndole un fin. Los cambios de un administrador no avisan al grupo.
- **Biblioteca**: las entradas de biblioteca de cada jugador, con su fecha de completado y la marca de abandonado.
- **Puntuaciones**: crear, cambiar y borrar notas de cualquier jugador.
- **Retos**: lanzar los retos del grupo (**Lanzar juego del mes** y **Lanzar reto temático**), con un interruptor para avisar al grupo, y borrar cualquiera (también los personales).

![Sesiones de todos los jugadores](../assets/screens/admin-timers.webp){ .screenshot }

![Retos del grupo](../assets/screens/admin-challenges.webp){ .screenshot }

## Notificaciones

- **Envíos**: el interruptor general de notificaciones, el de avisos a administradores, y los envíos programados: resumen semanal (día y hora), resumen mensual y resumen anual (apagados por defecto).
- **Canales**: Telegram (si está configurado y el mensaje de prueba) y avisos en la app (push: el interruptor y cuántos dispositivos hay suscritos). Lo que se configura en el `.env` se ve en **Sistema → Servicios**.
- **IA**: el interruptor de la IA, **Probar la IA** y los avisos que la usan, cada uno con su interruptor e instrucciones. El proveedor, la clave y el modelo se ven en **Sistema → Servicios**.
- **Probar resumen**: previsualiza el resumen de cualquier mes o temporada para cualquier jugador, enseña el aviso tal como saldría (sin enviarlo) y permite enviarlo ahora solo a ti o al grupo.
- **Redactar aviso**: escribe un mensaje propio, con título (80 caracteres) y mensaje (240), y envíalo por **un** canal: la **app** (push) o **Telegram**; a tus dispositivos, a un jugador, al grupo o a todos. Enviar al grupo o a todos pide confirmación.

![Los envíos programados](../assets/screens/admin-sends.webp){ .screenshot }

![Redactar un aviso](../assets/screens/admin-announce.webp){ .screenshot }

## Sistema

- **Chat**: interruptor del asistente de la app (el botón flotante), sus instrucciones y si los jugadores lo tienen disponible ahora (y, si no, por qué). Usa el proveedor y la clave de la IA de los avisos y, como modelo, `CHAT_AI_MODEL` (o `AI_MODEL` si no está): su interruptor y sus instrucciones son suyos, así que apagarlo aquí no afecta a los avisos ni al revés. Incluye un botón para probar el modelo.
- **Servicios**: lo que se configura en el `.env` del servidor y la app usa, junto: la **IA** (proveedor, clave y modelos, el de los avisos y el del chat), **Telegram** (token y chats: solo si están puestos), los **avisos en la app** (contacto y claves VAPID, con **Regenerar claves**) y el **correo** de recuperación de contraseña, con su correo de prueba (ver [Cuentas y acceso](cuentas.md)). Lo único editable es el contacto del push; lo demás solo se ve.
- **Copia de seguridad**: **Descargar copia (.sql.gz)** genera un volcado completo de la base de datos (usuarios, sesiones, biblioteca, logros, ajustes y fotos). Ver [Operación](operacion.md).
- **Registro**: qué ha cambiado cada administrador desde el panel, de lo más reciente a lo más antiguo, con un **Ver** que despliega cómo estaba antes y qué se envió. Se puede filtrar por usuario, tipo (cambios del panel o accesos y seguridad), sección y tipo de acción. También anota los accesos y los intentos fallidos de cualquier cuenta (y cuándo una cuenta queda bloqueada unos minutos), los cambios y recuperaciones de contraseña, los cambios del propio email o id de Telegram y los intentos de entrar al panel sin ser administrador, con la dirección y el navegador desde los que se hicieron. También anota cada vez que la IA se queda sin cupo (qué cupo, su límite y cuánto esperar), que es la forma de saber cuánto da el nivel gratuito de tu proveedor. Las contraseñas, tokens y claves nunca aparecen; lo demás que hacen los jugadores en su cuenta no se registra.

![El registro de cambios](../assets/screens/admin-audit.webp){ .screenshot }
