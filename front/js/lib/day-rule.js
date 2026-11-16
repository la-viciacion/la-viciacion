// What makes a day count as played, said once: the days played, the streaks and the achievements of both use it
// (api: played_days_by_user), so every place that shows one of those figures explains it with the same words.

/** The rule, as the text of an "i" (infoTip). */
export const DAY_RULE = 'Un día cuenta como jugado cuando hay al menos una sesión de 10 minutos o más. '
  + 'Se mira cada sesión por separado: varias sesiones cortas no se suman. Las horas sí cuentan siempre, dure lo que dure cada sesión.';
