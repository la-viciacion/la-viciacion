// Closing a poll of the Telegram group (admin panel → Notificaciones → Encuestas). It is closed in the app whatever Telegram
// does; asking again for one Telegram did not stop tries once more to stop it there, and announces nothing.
import { api, jsonRequest } from '../../lib/api.js';
import { html } from '../../lib/html.js';
import { toast } from '../../ui/toast.js';
import { ask } from './challenge-decisions.js';

/** Close it (and, if it is not stopped in Telegram, stop it there), telling the group the winner or not. */
export function closePoll(row, admin) {
  const closed = row.status === 'closed';
  ask({
    title: `${closed ? 'Cerrar en Telegram' : 'Cerrar'} · ${row.question}`,
    admin,
    submit: closed ? 'Intentarlo de nuevo' : 'Cerrar encuesta',
    body: closed
      ? html`<p class="adm-sub">La encuesta ya está cerrada aquí: los votos nuevos no cuentan. Se intenta pararla también en Telegram, sin avisar otra vez al grupo.</p>`
      : html`
        <p class="adm-sub">Deja de contar votos y se para en Telegram. Si Telegram falla, queda cerrada aquí igualmente y se vuelve a intentar sola.</p>
        <label class="adm-check"><input type="checkbox" name="announce" checked /> Avisar al grupo de la opción ganadora</label>`,
    run: async (el) => {
      const body = await api(`/manage/polls/${row.id}/close`, jsonRequest('POST', { announce: closed ? false : el.announce.checked }));
      toast(body.telegram_stopped ? 'Encuesta cerrada' : 'Cerrada aquí; Telegram no la ha parado todavía', body.telegram_stopped ? undefined : 'err');
    },
  });
}
