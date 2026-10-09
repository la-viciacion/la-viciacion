// Challenges page (#/challenges): time-boxed goals made from templates. GET /challenges has the definitions with their
// progress, derived from the sessions; only the definition is stored. A group challenge is the app's: every active
// player takes part (any may leave it) and an admin launches and deletes it from the admin panel (Gestión de datos →
// Retos). From this page a player launches and deletes only their own, personal challenges.
import { api, jsonRequest } from '../../lib/api.js';
import { DURATIONS, amountLabel, blocks, debtPreview, partTarget, partValue, percent, periodLine, summaryLine, timeLeft, totalPart } from '../../lib/challenges.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { toast } from '../../ui/toast.js';

export const active = null; // it belongs to no item of the top bar

let main;
let user;

const bar = (part) => html`<div class="ch-bar${part.done ? ' ok' : ''}"><i style="width:${percent(partValue(part), partTarget(part))}%"></i></div>`;

const partRow = (p, me) => html`
  <div class="ch-row">
    <span class="ch-name">${p.name}${p.user_id === me ? ' (tú)' : ''}</span>
    ${bar(p)}
    <span class="pf-sub">${amountLabel(p)}${p.done ? ' ✓' : ''}</span>
  </div>`;

const totalRow = (part) => html`
  <div class="ch-row ch-total">
    <span class="ch-name">Total</span>
    ${bar(part)}
    <span class="pf-sub">${amountLabel(part)}${part.done ? ' ✓' : ''}</span>
  </div>`;

function card(c) {
  const mine = c.scope === 'user' && c.owner?.id === user.id;
  const total = totalPart(c.progress);
  const parts = html`<div class="ch-players">${c.progress.players.map((p) => partRow(p, user.id))}</div>${total ? totalRow(total) : ''}`;
  return html`
    <article class="pf-card ch-card" data-challenge="${c.id}">
      <div class="ch-head">
        <div class="ch-title">
          ${c.game ? html`<a class="game-link" href="${gameHref(c.game.id)}">${c.title}</a>` : c.title}
          <div class="pf-sub">${c.scope === 'user' && !mine ? `${c.owner?.name ?? 'Alguien'} · ` : ''}${periodLine(c)}</div>
        </div>
        <span class="${c.status === 'active' ? 'pf-tag' : 'pf-tag muted'}">${timeLeft(c)}</span>
      </div>
      <div class="pf-sub">${summaryLine(c)}</div>
      ${c.taking_part || c.scope === 'user' ? parts : html`<div class="pf-empty">No participas en este reto.</div>`}
      <div class="ch-actions">
        ${c.can_opt_out
          ? html`<button class="pf-btn" type="button" data-part="${c.taking_part ? 'leave' : 'join'}">${c.taking_part ? 'Dejar de participar' : 'Volver a participar'}</button>`
          : ''}
        ${mine ? html`<button class="pf-btn" type="button" data-delete>Borrar</button>` : ''}
      </div>
    </article>`;
}

const section = ({ title, list, empty }) => html`
  <div class="section-header"><h2 class="section-title">${title}</h2><div class="section-line"></div></div>
  ${list.length ? html`<div class="ch-list">${list.map(card)}</div>` : html`<div class="pf-empty">${empty}</div>`}`;

function draw(challenges) {
  mount(main.querySelector('#chLists'), html`${blocks(challenges, user.id).map(section)}`);
}

async function load() {
  try {
    const challenges = await api('/challenges');
    if (challenges) draw(challenges);
  } catch (err) {
    mount(main.querySelector('#chLists'), html`<div class="pf-empty">Error cargando los retos: ${err.message}</div>`);
  }
}

async function change(id, path, options) {
  try {
    await api(`/challenges/${id}${path}`, options);
    await load();
  } catch (err) {
    toast(err.message, 'err');
  }
}

/** The form to launch a personal challenge: pick the kind, then its options. */
async function launchChallenge() {
  let genres;
  let debt;
  try {
    [genres, debt] = await Promise.all([api('/challenges/genres'), api('/challenges/debt')]);
  } catch (err) {
    toast(err.message, 'err');
    return;
  }
  const m = openModal(html`
    ${modalHeader('Nuevo reto')}
    <form class="adm-form" novalidate>
      <label>Tipo de reto<select class="adm-input" name="kind">
        <option value="new_genre">Probar un género</option>
        <option value="debt_reduction">Bajar la deuda</option>
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
    form.querySelectorAll('[data-kind]').forEach((box) => { box.hidden = box.dataset.kind !== kind; });
    const hoursField = form.querySelector('[data-for="play"]');
    if (hoursField) hoursField.hidden = el.mode?.value !== 'play';
    const percent = el.debtMode.value === 'percent';
    form.querySelector('[data-debt-label]').textContent = percent ? 'Porcentaje de la deuda' : 'Juegos a cerrar';
    el.debtValue.max = percent ? '100' : String(Math.max(1, debt.open_games));
    preview.textContent = debtPreview(el.debtMode.value, Number(el.debtValue.value), debt);
  };
  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  refresh();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const duration = el.duration.value;
    let body;
    if (el.kind.value === 'new_genre') {
      const options = { genre: el.genre?.value, mode: el.mode?.value, duration };
      if (options.mode === 'play') options.hours = Number(el.hours.value);
      body = { kind: 'new_genre', options };
    } else {
      const options = { mode: el.debtMode.value, duration };
      options[options.mode === 'percent' ? 'percent' : 'games'] = Number(el.debtValue.value);
      body = { kind: 'debt_reduction', options };
    }
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
      <button class="pf-btn primary" type="button" id="chNew">Nuevo reto</button>
    </div>
    <p class="pf-sub cal-intro">Objetivos con fecha de fin. Los del grupo los lanza un administrador y cada uno puede salirse; los tuyos los lanzas tú y los ven los demás.</p>
    <div id="chLists"><div class="loading-spinner">Cargando los retos...</div></div>`);
  main.querySelector('#chNew').addEventListener('click', launchChallenge);
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
