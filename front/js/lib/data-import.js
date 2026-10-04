// "Importar datos" of the profile: reading the file the person chose and wording what the API answered.
// Pure (no DOM, no fetch), so it can be tested.

export const EXPORT_FORMAT = 'laviciacion-export';
const MAX_BYTES = 8 * 1024 * 1024; // what the server's proxy accepts

const KINDS = [
  ['sessions', 'sesiones'],
  ['library', 'juegos en la biblioteca'],
  ['scores', 'puntuaciones'],
  ['wishlist', 'deseados'],
];

/** The export a text holds, or an Error saying why it is not one. */
export function parseExport(text, size = text.length) {
  if (size > MAX_BYTES) throw new Error('El archivo es demasiado grande (máximo 8 MB)');
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error('El archivo no es un JSON válido');
  }
  if (!data || data.format !== EXPORT_FORMAT) throw new Error('El archivo no es una exportación de La Viciación');
  return data;
}

/** What the file holds, for the question before importing: "12 sesiones, 3 juegos en la biblioteca". */
export function describeFile(data) {
  const parts = KINDS.map(([key, label]) => [data[key]?.length || 0, label]).filter(([n]) => n > 0);
  return parts.length ? parts.map(([n, label]) => `${n} ${label}`).join(', ') : 'nada que importar';
}

/** One line per kind of row that did something: "Sesiones: 8 nuevas, 2 que ya tenías, 1 no se puede importar". */
export function summarize(report) {
  const lines = [];
  for (const [key, label] of KINDS) {
    const { imported, existing, skipped } = report[key];
    const parts = [];
    if (imported) parts.push(`${imported} ${imported === 1 ? 'nueva' : 'nuevas'}`);
    if (existing) parts.push(`${existing} que ya tenías`);
    if (skipped) parts.push(`${skipped} no se ${skipped === 1 ? 'puede' : 'pueden'} importar`);
    if (parts.length) lines.push(`${label[0].toUpperCase()}${label.slice(1)}: ${parts.join(', ')}`);
  }
  const created = [];
  if (report.created.games) created.push(`${report.created.games} ${report.created.games === 1 ? 'juego' : 'juegos'}`);
  if (report.created.platforms) created.push(`${report.created.platforms} ${report.created.platforms === 1 ? 'plataforma' : 'plataformas'}`);
  if (created.length) lines.push(`${report.dry_run ? 'Se añadirían' : 'Añadidos'} al catálogo: ${created.join(' y ')}`);
  return lines;
}

/** Whether the import would add anything at all. */
export const addsSomething = (report) => KINDS.some(([key]) => report[key].imported > 0) || report.created.games > 0 || report.created.platforms > 0;
