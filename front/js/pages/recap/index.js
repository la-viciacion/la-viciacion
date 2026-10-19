// Recap (#/recap[/<period>[/<username>]]): "Wrapped" of a month or a season, yours and the group's.
// GET /statistics/recap/{period}?username=. Nothing is stored: the API derives it from the sessions when asked.
// The period opens on the month that has just ended; any past month or season can be chosen. An admin can add a
// player's username to the address to see theirs.
import { api } from '../../lib/api.js';
import { formatDate, formatDuration } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { storyHref } from '../../lib/story.js';
import { change, clampPick, lastMonth, monthChoices, parseHash, periodKey, periodLabel, pickOf, previousPeriod, recapHref, withKind, yearChoices } from '../../lib/recap.js';
import { statTile } from '../../ui/profile-summary.js';

export const active = null; // it belongs to no item of the top bar

let main;
let me;
let period;
let pick; // the period as a choice: monthly or annual, the year and, for a month, the month
let explicit = false; // the address names the period: because it came so or because it was chosen; #/recap stays #/recap until then
let username; // whose recap: yours unless an admin asks for another player's
let view = 'player'; // 'player' | 'group'
let data = null;
let navigation = 0; // only the latest request may draw

const cover = (game) => (game.image_url
  ? html`<img class="rc-cover" src="${game.image_url}" alt="" loading="lazy" />`
  : html`<div class="rc-cover rc-cover-placeholder" aria-hidden="true">🎮</div>`);

const trend = (now, before) => {
  const { text, trend: direction } = change(now, before, formatDuration);
  return html`<span class="rc-trend ${direction}">${text}</span>`;
};

const hero = (label, seconds, before, extra) => html`
  <div class="rc-hero">
    <div class="rc-hero-label">${label}</div>
    <div class="rc-hero-value">${formatDuration(seconds)}</div>
    <div class="rc-hero-sub">${trend(seconds, before)} frente a ${periodLabel(previousPeriod(period))} (${formatDuration(before)})</div>
    ${extra}
  </div>`;

const moment = (title, body) => html`<div class="pf-card rc-moment"><div class="rc-moment-title">${title}</div>${body}</div>`;

const holders = (n, own) => (n === 1 ? (own ? 'solo lo tienes tú' : 'solo lo tiene una persona') : `${n} jugadores lo tienen`);

/** The player's own recap. */
export function playerView(p) {
  if (!p.seconds) return html`<div class="empty-state"><span>🎮</span>No se jugó nada en ${periodLabel(period)}.</div>`;
  return html`
    ${hero(otherPlayer() ? 'Ha jugado' : 'Has jugado', p.seconds, p.previous_seconds, p.position ? html`<div class="rc-hero-sub">Puesto <strong>${p.position}º</strong> del grupo</div>` : '')}
    <div class="pf-stats">
      ${statTile('Sesiones', p.sessions)}
      ${statTile('Días', p.days)}
      ${statTile('Juegos', p.games)}
      ${statTile('Mejor racha', `${p.best_streak} d`)}
      ${statTile('Sesión más larga', formatDuration(p.longest_session))}
    </div>
    <div class="rc-moments">
      ${p.star_game ? moment('⭐ Juego estrella', html`
        <div class="rc-game">${cover(p.star_game)}<div><a class="game-link rc-name" href="${gameHref(p.star_game.id)}">${p.star_game.name}</a><div class="pf-sub">${formatDuration(p.star_game.seconds)}</div></div></div>`) : ''}
      ${p.best_day ? moment('🔥 Mejor día', html`<div class="rc-name">${formatDate(p.best_day)}</div><div class="pf-sub">${formatDuration(p.best_day_seconds)} jugados</div>`) : ''}
      ${p.playmate ? moment('🤝 Con quien más ha jugado', html`<div class="rc-name">${p.playmate.name}</div><div class="pf-sub">${formatDuration(p.playmate.seconds)} juntos en el mismo juego</div>`) : ''}
      ${p.games_started || p.games_completed ? moment('📚 Biblioteca', html`<div class="rc-name">${p.games_started} empezados · ${p.games_completed} completados</div>`) : ''}
      ${p.achievements ? moment('🏆 Logros', html`
        <div class="rc-name">${p.achievements} ${p.achievements === 1 ? 'logro' : 'logros'}</div>
        ${p.rarest_achievement ? html`<div class="pf-sub">El más raro: <strong>${p.rarest_achievement.title}</strong> (${holders(p.rarest_achievement.holders, true)})</div>` : ''}`) : ''}
    </div>`;
}

/** The group's recap. */
export function groupView(g) {
  if (!g.seconds) return html`<div class="empty-state"><span>🎮</span>Nadie jugó en ${periodLabel(period)}.</div>`;
  const most = g.ranking[0].seconds;
  return html`
    ${hero('El grupo ha jugado', g.seconds, g.previous_seconds, '')}
    <div class="pf-stats">
      ${statTile('Jugadores', g.players)}
      ${statTile('Sesiones', g.sessions)}
      ${g.achievements ? statTile('Logros', g.achievements) : ''}
    </div>
    <div class="section-header"><h2 class="section-title">Clasificación</h2><div class="section-line"></div></div>
    <div class="pf-card" id="rcRanking">
      ${g.ranking.map((row, i) => html`
        <div class="pf-bar-row">
          <div class="pf-bar-label"><span>${['🥇', '🥈', '🥉'][i] || `${i + 1}.`} ${row.name}</span><span>${formatDuration(row.seconds)} ${trend(row.seconds, row.previous_seconds)}</span></div>
          <div class="pf-bar"><div style="width:${Math.max(3, Math.round((row.seconds / most) * 100))}%"></div></div>
        </div>`)}
    </div>
    ${g.top_games.length ? html`
      <div class="section-header"><h2 class="section-title">Juegos del periodo</h2><div class="section-line"></div></div>
      <div class="rc-moments" id="rcGames">
        ${g.top_games.map((game) => moment(`${formatDuration(game.seconds)} · ${game.players} ${game.players === 1 ? 'jugador' : 'jugadores'}`, html`
          <div class="rc-game">${cover(game)}<a class="game-link rc-name" href="${gameHref(game.id || game.game_id)}">${game.name || game.game_id}</a></div>`))}
      </div>` : ''}
    <div class="rc-moments">
      ${g.busiest_day ? moment('🔥 Día más movido', html`<div class="rc-name">${formatDate(g.busiest_day)}</div><div class="pf-sub">${formatDuration(g.busiest_day_seconds)} entre todos</div>`) : ''}
      ${g.rarest_achievement ? moment('🏆 Logro más raro', html`<div class="rc-name">${g.rarest_achievement.title}</div><div class="pf-sub">${holders(g.rarest_achievement.holders, false)}</div>`) : ''}
    </div>`;
}

const otherPlayer = () => username && username !== me.username;

// Monthly or annual, then the year (and the month): a short list at each step instead of one that grows every month
function picker() {
  const selected = (on) => (on ? 'selected' : '');
  return html`
    <label class="rc-select">Resumen
      <select class="adm-input" id="rcKind">
        <option value="month" ${selected(pick.kind === 'month')}>Mensual</option>
        <option value="year" ${selected(pick.kind === 'year')}>Anual</option>
      </select>
    </label>
    <label class="rc-select">Año
      <select class="adm-input" id="rcYear">${yearChoices().map((year) => html`<option value="${year}" ${selected(year === pick.year)}>${year}</option>`)}</select>
    </label>
    ${pick.kind === 'month' ? html`
      <label class="rc-select">Mes
        <select class="adm-input" id="rcMonth">${monthChoices(pick.year).map(({ value, label }) => html`<option value="${value}" ${selected(value === pick.month)}>${label}</option>`)}</select>
      </label>` : ''}`;
}

function header() {
  return html`
    <div class="rc-head">
      <h1 class="pf-title pg-title">Resumen</h1>
      <div class="rc-picker">${picker()}</div>
    </div>
    <a class="pf-btn rc-story" id="rcStory" href="${storyHref(period, otherPlayer() ? username : null)}">▶ Ver como historia</a>
    <div class="gc-toggles" role="tablist">
      <button type="button" class="gc-toggle" role="tab" data-view="player" aria-pressed="${String(view === 'player')}">${otherPlayer() ? username : 'Tú'}</button>
      <button type="button" class="gc-toggle" role="tab" data-view="group" aria-pressed="${String(view === 'group')}">El grupo</button>
    </div>`;
}

function draw() {
  const running = data && !data.complete;
  mount(main, html`
    ${header()}
    ${running ? html`<div class="pf-sub rc-running">${periodLabel(period)} todavía no ha terminado: son los datos hasta hoy.</div>` : ''}
    <div id="rcBody">${view === 'player' ? playerView(data.player) : groupView(data.group)}</div>`);
}

async function load() {
  const id = ++navigation;
  if (explicit) history.replaceState(null, '', recapHref(period, otherPlayer() ? username : null));
  mount(main, html`${header()}<div id="rcBody" class="pf-sub">Cargando…</div>`);
  try {
    const result = await api(`/statistics/recap/${period}?username=${encodeURIComponent(username || me.username)}`);
    if (id !== navigation) return;
    data = result;
    draw();
  } catch (err) {
    if (id !== navigation) return;
    data = null;
    mount(main, html`${header()}<div class="empty-state"><span>⚠️</span>${err.message}</div>`);
  }
}

export async function render({ user, main: target }) {
  main = target;
  me = user;
  const asked = parseHash(location.hash);
  explicit = Boolean(asked.period);
  pick = clampPick(pickOf(asked.period || lastMonth()));
  period = periodKey(pick);
  username = user.is_admin ? asked.username : null;
  view = 'player';
  data = null;
  main.onchange = (event) => {
    const { id, value } = event.target;
    if (id === 'rcKind') pick = withKind(pick, value);
    else if (id === 'rcYear') pick = clampPick({ ...pick, year: Number(value) });
    else if (id === 'rcMonth') pick = { ...pick, month: Number(value) };
    else return;
    period = periodKey(pick);
    explicit = true; // a period was chosen: now the address says which
    load();
  };
  main.onclick = (event) => {
    const button = event.target.closest('[data-view]');
    if (!button || !data) return;
    view = button.dataset.view;
    draw();
  };
  await load();
}
