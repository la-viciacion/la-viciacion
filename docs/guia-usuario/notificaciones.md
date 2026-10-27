# Notificaciones y Telegram

La Viciación avisa por dos canales: **Telegram** (un grupo y un bot) y las **notificaciones del móvil o del navegador** (push). Cada jugador elige lo que quiere recibir en privado.

## Qué se avisa

**Al grupo** (en el grupo de Telegram y como notificación en los dispositivos que tengan activados los avisos del grupo):

- Un logro conseguido (los secretos, sin detalles).
- Un juego completado, con su duración y, a veces, una recomendación.
- Un juego jugado por primera vez por alguien.
- Cambios en los rankings de horas y de juegos.
- Rachas perdidas (cada día a las 05:00 se anuncian las del día anterior).
- Los lanzamientos de la lista de deseados: **el día antes** de que salga un juego (lo normal) o, si el administrador lo prefiere, **un resumen cada domingo** con los que salen en los 7 días siguientes. Nunca los dos.
- El resumen mensual o anual y los retos del grupo: cuando se lanza uno, cuando el grupo llega al total y, al día siguiente de que acabe, cómo ha terminado.

Los textos pueden estar escritos por una IA para que sean más graciosos, si el administrador la ha configurado.

**A ti en privado:**

- El **resumen semanal**, si el administrador lo tiene activado.
- Un aviso de **timer olvidado**, una sola vez por timer.
- **Tus retos**: que te han retado a un duelo, que te han rechazado uno, cómo se ha contestado una propuesta tuya y cómo han terminado los retos en los que participas (un solo mensaje al día, con todos). Los retos personales y los duelos **nunca** se avisan al grupo.
- Un **recordatorio** cuando a un reto tuyo le quedan 2 días y aún no lo has cumplido (viene **desactivado**: lo activas en **Perfil → Ajustes → Notificaciones**).
- Los logros secretos que consigues, completos.
- **Sale un juego deseado**: el día que sale un juego de tu lista de deseados, con quién más lo espera (un solo mensaje con todos los de ese día).

Cuando un aviso nombra un juego, el nombre es un **enlace**: en Telegram te lleva a su página de RAWG o a su página en la app, según el aviso. En las notificaciones del móvil el nombre sale como texto normal; los enlaces los encuentras en Avisos.

## Avisos dentro de la app

La campana de la barra superior abre **Avisos**: lo que se ha dicho al grupo y lo que te han dicho a ti, para quien se perdió una notificación o las tiene desactivadas. Funciona sin Telegram ni notificaciones push. Un número en la campana cuenta los que no has leído; al abrir la página quedan marcados como leídos (los nuevos se ven resaltados hasta tu próxima visita).

- Pulsa un aviso para ir a la página a la que se refiere.
- Bórralos de uno en uno con la **×**, o todos con **Vaciar todo** (pide una segunda pulsación). Es solo tu bandeja: lo que borras no desaparece para los demás.
- Se guardan unos días (14 por defecto, lo decide el administrador) y luego se borran solos.
- Los avisos del cronómetro (que empezaste o paraste un timer, o el de timer olvidado) no se guardan aquí.

## Telegram

### Vincular tu cuenta

El bot solo atiende a los miembros del grupo con cuenta en la app. Para que te reconozca:

1. Ten un **nombre de usuario de Telegram** (`@algo`) en los ajustes de Telegram.
2. Pide a un administrador que tu **usuario de la app** sea el mismo que tu `@usuario` de Telegram (da igual mayúsculas o minúsculas).
3. Escribe `/activate` **en el grupo**. El bot guarda tu identificador de Telegram y, a partir de ahí, ya no importa que cambies de `@usuario`.

Cuando entras al grupo, el bot te da la bienvenida y te recuerda este paso.

También puedes poner tu **Telegram ID** a mano en **Perfil → Ajustes → Perfil** y probarlo con **Enviar mensaje de prueba**.

### El menú del bot

Escribe `/menu` (en privado o en el grupo) para consultar tus estadísticas y los rankings sin abrir la app:

| Menú | Opciones |
|---|---|
| 🕺 **Mis estadísticas** | Juegos, completados, top juegos, logros, racha. |
| 🏅 **Rankings** | Días, horas, jugados, completados, logros, ratio, racha actual y máxima, más jugados, deuda y deuda total. |
| 🎲 **Recomendados** | Juegos que tienen otros jugadores y tú no. |

Los botones de un menú son solo de quien lo abrió: si pulsas los de otra persona, o los de un menú antiguo (por ejemplo, de antes de un reinicio del bot), te sale un aviso y basta con escribir `/menu` para abrir el tuyo.

El bot es de **solo lectura**: no registra sesiones, solo consulta. Las cuentas desactivadas no aparecen en sus rankings.

## Notificaciones en el móvil (push)

1. Instala la [PWA](primeros-pasos.md) (en iPhone es obligatorio) y acepta el aviso que te ofrece la app, o actívalas desde **Perfil → Ajustes → Notificaciones**.
2. El navegador te pedirá permiso: acéptalo.
3. En la tarjeta de dispositivos eliges, **para cada uno**, si recibe también los avisos del grupo.

Mientras tienes un timer en marcha, tus dispositivos muestran una notificación fija y silenciosa con el juego; al tocarla (o su botón **Parar**) se abre la app para detenerlo. En iPhone no queda fijada y no tiene botón.

## Elegir qué recibes

En **Perfil → Ajustes → Notificaciones** hay una tabla con los avisos privados y, para cada uno, una casilla de **Telegram** y otra de **Push**. Un aviso sin ningún canal marcado simplemente no se envía. Telegram solo llega si has vinculado tu cuenta, y push solo si has activado los avisos en algún dispositivo.

Los avisos que tienen opciones propias se despliegan bajo su fila mientras haya algún canal marcado, y se guardan con su botón **Guardar**. Para el aviso de **timer olvidado** eliges a partir de cuántas horas (entre 1 y 24; 4 por defecto). Se comprueba cada hora, así que puede llegar hasta una hora después.
