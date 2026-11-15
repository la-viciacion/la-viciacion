// One-off: ask IGDB which games went into early access (and when) for the whole catalogue, to fill what was there before the
// column existed. It only reads and writes dates, a few requests in all, so one confirmation is enough (no typed phrase).
import { api } from '../../lib/api.js';
import { html } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { confirmDialog } from './dialogs.js';

export async function earlyAccessScanFlow({ onDone } = {}) {
  const ok = await confirmDialog(
    'Detectar early access',
    html`<p>Pregunta a IGDB, de una vez, qué juegos del catálogo con ID de IGDB han tenido early access y desde cuándo, y también su lanzamiento oficial. <strong>Solo escribe fechas</strong>: nunca borra una que ya haya. Cada día se mantienen solas.</p>`,
    { ok: 'Detectar' },
  );
  if (!ok) return;
  try {
    const { asked, changed, failed } = await api('/manage/igdb-sync/early-access', { method: 'POST' });
    toast(`${asked} consultados, ${changed} actualizados${failed ? `, ${failed} sin respuesta de IGDB` : ''}`);
    onDone?.();
  } catch (err) {
    toast(err.message);
  }
}
