// Challenges page (#/challenges): time-boxed goals made from templates. GET /challenges has the definitions with their
// progress, derived from the sessions; only the definition is stored. A group challenge is the app's: every active
// player takes part (any may leave it) and an admin launches and deletes it from the admin panel (Gestión de datos →
// Retos). From this page a player launches and deletes only their own, personal challenges.
import { api, jsonRequest } from '../../lib/api.js';
import { DURATIONS, PERSONAL_KINDS, amountLabel, blocks, debtPreview, digest, digestLine, medal, partTarget, partValue, percent, periodLine, standing, summaryLine, timeLeft, totalPart } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';
import { gameSearch, gameSearchField } from './game-search.js';
import { openProposalForm, showProposals } from './proposals.js';

export const active = null; // it belongs to no item of the top bar

let main;
let user;

const bar = (part) => html`<div class="ch-bar${part.done ? ' ok' : ''}"><i style="width:${percent(partValue(part), partTarget(part))}%"></i></div>`;

const partRow = (p, me, ranked) => html`
  <div class="ch-row">
    <span class="ch-name">${ranked && p.position ? `${medal(p.position)} ` : ''}${p.name}${p.user_id === me ? ' (tú)' : ''}</span>
    ${bar(p)}
    <span class="pf-sub">${amountLabel(p)}${p.done ? ' ✓' : ''}</span>
  </div>`;

const totalRow = (part) => html`
  <div class="ch-row ch-total">
    <span class="ch-name">Total</span>
    ${bar(part)}
    <span class="pf-sub">${amountLabel(part)}${part.done ? ' ✓' : ''}</span>
  </div>`;

const standingLine = (c) => {
  const s = standing(c, user.id);
  return s ? html`<div class="ch-standing ${s.tone}" data-standing="${s.tone}">${s.text}</div>` : '';
};

const sub = (c) => {
  if (c.scope === 'duel') return `${c.owner?.name} contra ${c.opponent?.name} · ${periodLine(c)}`;
  return `${c.scope === 'user' && c.owner?.id !== user.id ? `${c.owner?.name ?? 'Alguien'} · ` : ''}${periodLine(c)}`;
};

// the button of whoever can change their part: leave (or join) a group challenge, or turn a duel down (final)
const partButton = (c) => {
  if (!c.can_opt_out) return '';
  const voluntary = c.participation === 'opt_in';
  const label = c.scope === 'duel' ? 'Rechazar duelo' : (c.taking_part ? 'Dejar de participar' : voluntary ? 'Apuntarme' : 'Volver a participar');
  return html`<button class="pf-btn" type="button" data-part="${c.taking_part ? 'leave' : 'join'}">${label}</button>`;
};

function card(c) {
  const mine = c.scope !== 'group' && c.owner?.id === user.id;
  const total = totalPart(c.progress);
  const ranked = Boolean(c.params?.versus) || c.scope === 'duel';
  const parts = html`<div class="ch-players">${c.progress.players.map((p) => partRow(p, user.id, ranked))}</div>${total ? totalRow(total) : ''}`;
  return html`
    <article class="pf-card ch-card" data-challenge="${c.id}">
      <div class="ch-head">
        <div class="ch-title">
          ${c.game ? html`<a class="game-link" href="${gameHref(c.game.id)}">${c.title}</a>` : c.title}${c.participation === 'opt_in' ? html` <span class="pf-tag muted">Voluntario</span>` : ''}
          <div class="pf-sub">${sub(c)}</div>
        </div>
        <span class="${c.status === 'active' && !c.declined ? 'pf-tag' : 'pf-tag muted'}">${c.declined ? 'Rechazado' : timeLeft(c)}</span>
      </div>
      <div class="pf-sub">${summaryLine(c)}</div>
      ${standingLine(c)}
      ${c.taking_part || c.scope !== 'group' ? parts : html`<div class="pf-empty">${c.participation === 'opt_in' ? 'Es un reto voluntario: apúntate si quieres jugarlo.' : 'No participas en este reto.'}</div>`}
      ${c.scope === 'duel' && c.can_opt_out && c.taking_part ? html`<div class="pf-sub">Puedes rechazarlo durante las 48 horas siguientes a su lanzamiento.</div>` : ''}
      <div class="ch-actions">
        ${partButton(c)}
        ${mine ? html`<button class="pf-btn" type="button" data-delete>Borrar</button>` : ''}
      </div>
    </article>`;
}

const section = ({ title, list, empty }) => html`
  <div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>
  ${list.length ? html`<div class="ch-list">${list.map(card)}</div>` : html`<div class="pf-empty">${empty}</div>`}`;

function draw(challenges) {
  const line = digestLine(digest(challenges, user.id));
  mount(main.querySelector('#chDigest'), html`${line ? html`<p class="ch-digest" data-digest>${line}</p>` : ''}`);
  mount(main.querySelector('#chLists'), html`${blocks(challenges, user.id).map(section)}`);
}

async function load() {
  try {
    const challenges = await api('/challenges');
    if (challenges) draw(challenges);
  } catch (err) {
    mount(main.querySelector('#chLists'), html`<div class="pf-empty">Error cargando los retos: ${err.message}</div>`);
  }
  await showProposals(main.querySelector('#chProposals'));
}

async function change(id, path, options) {
  try {
    await api(`/challenges/${id}${path}`, options);
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

// What each kind asks of the form: the options it sends (the duration is added to all of them)
const OPTIONS = {
  duel_hours: (el) => ({ opponent_id: Number(el.duelOpponent.value) }),
  duel_game: (el, state) => ({ opponent_id: Number(el.duelOpponent.value), game_id: state.game?.id }),
  new_genre: (el) => ({ genre: el.genre?.value, mode: el.mode?.value, ...(el.mode?.value === 'play' ? { hours: Number(el.hours.value) } : {}) }),
  debt_reduction: (el) => ({ mode: el.debtMode.value, [el.debtMode.value === 'percent' ? 'percent' : 'games']: Number(el.debtValue.value) }),
  streak: (el) => ({ mode: el.streakMode.value, days: Number(el.streakDays.value) }),
  long_sessions: (el) => ({ sessions: Number(el.longSessions.value), minutes: Number(el.longMinutes.value) }),
  variety: (el) => ({ genres: Number(el.varietyGenres.value), hours: Number(el.varietyHours.value) }),
  wishlist: (el) => ({ mode: el.wishMode.value, games: Number(el.wishGames.value) }),
};

/** The form to launch a personal challenge: pick the kind, then its options. */
async function launchChallenge() {
  let genres;
  let debt;
  let players;
  try {
    [genres, debt, players] = await Promise.all([api('/challenges/genres'), api('/challenges/debt'), api('/group/players').catch(() => [])]); // without the players only the duels cannot be launched
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  const m = openModal(html`
    ${modalHeader('Nuevo reto')}
    <form class="adm-form" novalidate>
      <label>Tipo de reto<select class="adm-input" name="kind">
        ${PERSONAL_KINDS.map(([value, label]) => html`<option value="${value}">${label}</option>`)}
      </select></label>

      <div data-kind="new_genre">
        <p class="adm-sub">Elige un género y cuánto quieres jugarlo. Solo cuentan los juegos de ese género que no tuvieras antes de empezar el reto, desde hoy.</p>
        ${genres?.length
          ? html`
            <label>Género<select class="adm-input" name="genre">
              ${genres.map((g) => html`<option value="${g.genre}">${g.genre} (${g.games})${g.played ? '' : ' · nuevo para ti'}</option>`)}
            </select></label>
            <label>Objetivo<select class="adm-input" name="mode">
              <option value="play">Jugar unas horas</option>
              <option value="complete">Completar un juego</option>
            </select></label>
            <label data-for="play">Horas<input class="adm-input" type="number" name="hours" min="0.5" step="0.5" value="2" /></label>`
          : html`<p class="adm-sub">Todavía no hay géneros en la base de datos.</p>`}
      </div>

      <div data-kind="debt_reduction" hidden>
        <p class="adm-sub">Solo cuenta lo que juegues en los juegos que ya tenías empezados al lanzar el reto: los juegos nuevos ni suman ni restan. Completar un juego salda lo que te quedaba de él; abandonarlo, no.</p>
        <label>Objetivo<select class="adm-input" name="debtMode">
          <option value="percent">Saldar un porcentaje de mi deuda</option>
          <option value="games">Cerrar juegos de mi deuda</option>
        </select></label>
        <label><span data-debt-label>Porcentaje de la deuda</span><input class="adm-input" type="number" name="debtValue" min="1" step="1" value="25" /></label>
        <p class="adm-sub" id="chDebtPreview" aria-live="polite"></p>
      </div>

      <div data-kind="duel_hours duel_game" hidden>
        <p class="adm-sub">Quien juegue más gana. Empieza hoy, y el otro jugador puede rechazarlo durante 48 horas.</p>
        <label>Retar a<select class="adm-input" name="duelOpponent">
          ${(players ?? []).filter((p) => p.is_active && !p.is_me).map((p) => html`<option value="${p.user_id}">${p.name}</option>`)}
        </select></label>
      </div>

      <div data-kind="duel_game" hidden>
        ${gameSearchField}
      </div>

      <div data-kind="streak" hidden>
        <p class="adm-sub">Un día cuenta cuando juegas al menos 10 minutos seguidos, como en las rachas y los logros.</p>
        <label>Objetivo<select class="adm-input" name="streakMode">
          <option value="consecutive">Días seguidos</option>
          <option value="days">Días distintos</option>
        </select></label>
        <label>Días<input class="adm-input" type="number" name="streakDays" min="2" max="90" step="1" value="5" /></label>
      </div>

      <div data-kind="long_sessions" hidden>
        <p class="adm-sub">Cuenta cada sesión terminada que dure al menos lo que pidas, sea del juego que sea.</p>
        <label>Sesiones<input class="adm-input" type="number" name="longSessions" min="1" max="100" step="1" value="3" /></label>
        <label>Minutos mínimos de cada una<input class="adm-input" type="number" name="longMinutes" min="15" max="600" step="5" value="60" /></label>
      </div>

      <div data-kind="variety" hidden>
        <p class="adm-sub">Juega a géneros distintos: un género cuenta cuando le dedicas las horas que pidas. El tiempo de un juego cuenta en cada uno de sus géneros.</p>
        <label>Géneros distintos<input class="adm-input" type="number" name="varietyGenres" min="2" max="10" step="1" value="3" /></label>
        <label>Horas mínimas en cada uno<input class="adm-input" type="number" name="varietyHours" min="0.5" step="0.5" value="1" /></label>
      </div>

      <div data-kind="wishlist" hidden>
        <p class="adm-sub">Solo cuentan los juegos que ya tenías en deseados (y no en tu biblioteca) el día que lanzas el reto. Si quitas uno de la lista, deja de contar.</p>
        <label>Objetivo<select class="adm-input" name="wishMode">
          <option value="start">Empezar juegos de mis deseados</option>
          <option value="complete">Completar juegos de mis deseados</option>
        </select></label>
        <label>Juegos<input class="adm-input" type="number" name="wishGames" min="1" step="1" value="1" /></label>
      </div>

      <label>Duración<select class="adm-input" name="duration">
        ${DURATIONS.map(([value, label]) => html`<option value="${value}" ${value === 'month' ? html`selected` : ''}>${label}</option>`)}
      </select></label>
      <div class="adm-error" role="alert"></div>
      <div class="adm-actions">
        <button type="button" class="adm-btn" data-close>Cancelar</button>
        <button type="submit" class="adm-btn primary">Lanzar reto</button>
      </div>
    </form>`);
  const form = m.el.querySelector('form');
  const el = form.elements;
  const preview = form.querySelector('#chDebtPreview');

  const refresh = () => {
    const kind = el.kind.value;
    form.querySelectorAll('[data-kind]').forEach((box) => { box.hidden = !box.dataset.kind.split(' ').includes(kind); });
    const hoursField = form.querySelector('[data-for="play"]');
    if (hoursField) hoursField.hidden = el.mode?.value !== 'play';
    const percent = el.debtMode.value === 'percent';
    form.querySelector('[data-debt-label]').textContent = percent ? 'Porcentaje de la deuda' : 'Juegos a cerrar';
    el.debtValue.max = percent ? '100' : String(Math.max(1, debt.open_games));
    preview.textContent = debtPreview(el.debtMode.value, Number(el.debtValue.value), debt);
  };
  const state = { game: null };
  gameSearch(form, state);
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  refresh();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const kind = el.kind.value;
    const body = { kind, options: { ...OPTIONS[kind](el, state), duration: el.duration.value } };
    try {
      await api('/challenges', jsonRequest('POST', body));
      m.close();
      toast('Reto lanzado');
      await load();
    } catch (err) {
      form.querySelector('.adm-error').textContent = err.message;
    }
  });
}

export async function render(ctx) {
  main = ctx.main;
  user = ctx.user;
  mount(main, html`
    <div class="wl-head">
      <h1 class="pf-title">Retos</h1>
      <div class="ch-head-actions">
        <button class="pf-btn" type="button" id="chPropose">Proponer al grupo</button>
        <button class="pf-btn primary" type="button" id="chNew">Nuevo reto</button>
      </div>
    </div>
    <p class="pf-sub cal-intro">Objetivos con fecha de fin. Los del grupo los lanza un administrador (puedes proponerle uno) y cada uno puede salirse, salvo los voluntarios, a los que hay que apuntarse; los tuyos los lanzas tú y los ven los demás.</p>
    <div id="chDigest"></div>
    <div id="chLists"><div class="loading-spinner">Cargando los retos...</div></div>
    <div id="chProposals"></div>`);
  main.querySelector('#chNew').addEventListener('click', launchChallenge);
  main.querySelector('#chPropose').addEventListener('click', () => openProposalForm(load));
  main.querySelector('#chLists').addEventListener('click', (e) => {
    const id = e.target.closest('[data-challenge]')?.dataset.challenge;
    const part = e.target.closest('[data-part]');
    if (id && part) change(id, `/participation?joined=${part.dataset.part === 'join'}`, { method: 'PUT' });
    const del = e.target.closest('[data-delete]');
    if (id && del) {
      // the second press confirms
      if (del.dataset.sure) change(id, '', { method: 'DELETE' });
      else {
        del.dataset.sure = '1';
        del.textContent = '¿Seguro? Pulsa otra vez';
      }
    }
  });
  await load();
}
