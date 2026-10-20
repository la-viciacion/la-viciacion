# Notificaciones y Telegram

La Viciación avisa por dos canales: **Telegram** (un grupo y un bot) y las **notificaciones del móvil o del navegador** (push). Cada jugador elige lo que quiere recibir en privado.

## Qué se avisa

**Al grupo** (en el grupo de Telegram y como notificación en los dispositivos que tengan activados los avisos del grupo):

- Un logro conseguido (los secretos, sin detalles).
- Un juego completado, con su duración y, a veces, una recomendación.
- Un juego jugado por primera vez por alguien.
- Cambios en los rankings de horas y de juegos.
- Rachas perdidas (cada día a las 05:00 se anuncian las del día anterior).
- El día antes de un lanzamiento deseado.
- El resumen mensual o anual y los retos del grupo.

Los textos pueden estar escritos por una IA para que sean más graciosos, si el administrador la ha configurado.

**A ti en privado:**

- El **resumen semanal**, si el administrador lo tiene activado.
- Un aviso de **timer olvidado**, una sola vez por timer.
- Los logros secretos que consigues, completos.

## Telegram

### Vincular tu cuenta

El bot solo atiende a los miembros del grupo con cuenta en la app. Para que te reconozca:

1. Ten un **nombre de usuario de Telegram** (`@algo`) en los ajustes de Telegram.
2. Pide a un administrador que tu **usuario de la app** sea el mismo que tu `@usuario` de Telegram (da igual mayúsculas o minúsculas).
3. Escribe `/activate` **en el grupo**. El bot guarda tu identificador de Telegram y, a partir de ahí, ya no importa que cambies de `@usuario`.

Cuando entras al grupo, el bot te da la bienvenida y te recuerda este paso.

También puedes poner tu **Telegram ID** a mano en **Perfil → Ajustes → Mis datos** y probarlo con **Enviar mensaje de prueba**.

### El menú del bot

Escribe `/menu` (en privado o en el grupo) para consultar tus estadísticas y los rankings sin abrir la app:

| Menú | Opciones |
|---|---|
| 🕺 **Mis estadísticas** | Juegos, completados, top juegos, logros, racha. |
| 🏅 **Rankings** | Días, horas, jugados, completados, logros, ratio, racha actual y máxima, más jugados, deuda y deuda total. |
| 🎲 **Recomendados** | Juegos que tienen otros jugadores y tú no. |

El menú se cierra solo al cabo de un minuto sin usarlo; si pulsas un botón de un menú caducado (o de otra persona) te sale un aviso y basta con escribir `/menu` otra vez.

El bot es de **solo lectura**: no registra sesiones, solo consulta. Las cuentas desactivadas no aparecen en sus rankings.

## Notificaciones en el móvil (push)

1. Instala la [PWA](primeros-pasos.md) (en iPhone es obligatorio) y acepta el aviso que te ofrece la app, o actívalas desde **Perfil → Ajustes → Notificaciones**.
2. El navegador te pedirá permiso: acéptalo.
3. En la tarjeta de dispositivos eliges, **para cada uno**, si recibe también los avisos del grupo.

Mientras tienes un timer en marcha, tus dispositivos muestran una notificación fija y silenciosa con el juego; al tocarla (o su botón **Parar**) se abre la app para detenerlo. En iPhone no queda fijada y no tiene botón.

## Elegir qué recibes

En **Perfil → Ajustes → Notificaciones** hay una tabla con los avisos privados y, para cada uno, una casilla de **Telegram** y otra de **Push**. Un aviso sin ningún canal marcado simplemente no se envía. Telegram solo llega si has vinculado tu cuenta, y push solo si has activado los avisos en algún dispositivo.

Para el aviso de **timer olvidado** también eliges a partir de cuántas horas (entre 1 y 24; 4 por defecto). Se comprueba cada hora, así que puede llegar hasta una hora después.
