// Release calendar (#/calendar): every game of the catalogue with a release date, by day, wanted by somebody or not. GET /group/releases?month=YYYY-MM; any month, past ones included.
// A day with releases opens a modal with its games (one or several, so every day behaves the same). The games with no confirmed date are listed apart. Nothing is stored here: the wishes are the only data.
import { api } from '../../lib/api.js';
import { byDay, monthLabel, monthOf, monthWeeks, shiftMonth, waiting } from '../../lib/calendar.js';
import { formatDate } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { modalHeader, openModal } from '../../ui/modal.js';
import { countdown } from '../../lib/wishlist.js';

export const active = null; // it belongs to no item of the top bar

const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

let main;
let current; // the running month, "YYYY-MM"
let shown; // the month on screen
let data = null; // the answer for `shown`
let navigation = 0; // only the latest request may draw

const byRelease = (a, b) => a.release_date.localeCompare(b.release_date) || a.name.localeCompare(b.name);

// inModal: following the link must also close the modal, which the router knows nothing about
const card = (g, inModal = false) => html`
  <a class="gc-card cal-game" href="${gameHref(g.id)}" ${inModal ? 'data-close' : ''}>
    ${g.image_url
      ? html`<img src="${g.image_url}" alt="" class="gc-cover" loading="lazy" />`
      : html`<div class="gc-cover gc-cover-placeholder" aria-hidden="true">🎮</div>`}
    <div class="gc-body">
      <div class="gc-name">${g.name}</div>
      <div class="gc-tags">${g.genres.slice(0, 2).map((genre) => html`<span class="pf-tag muted">${genre}</span>`)}</div>
      <div class="gc-meta"><span>${[countdown(g), g.release_date && formatDate(g.release_date)].filter(Boolean).join(' · ')}</span></div>
      <div class="pf-sub">${waiting(g.wanted_by)}</div>
    </div>
  </a>`;

function cell(day, games, today) {
  if (!day) return html`<div class="cal-cell blank" aria-hidden="true"></div>`;
  const classes = ['cal-cell', games ? 'has' : '', day === today ? 'today' : ''].filter(Boolean).join(' ');
  const number = Number(day.slice(8));
  if (!games) return html`<div class="${classes}"><span class="cal-day">${number}</span></div>`;
  const label = `${number}: ${games.map((g) => g.name).join(', ')}`;
  const thumb = games[0].image_url ? html`<img class="cal-thumb" src="${games[0].image_url}" alt="" loading="lazy" />` : '';
  return html`
    <button class="${classes}" type="button" data-day="${day}" title="${games.map((g) => g.name).join(', ')}" aria-label="${label}">
      <span class="cal-day">${number}</span>
      ${thumb}
      <span class="cal-count">${games.length === 1 ? games[0].name : `${games.length} juegos`}</span>
    </button>`;
}

function openDay(day) {
  const games = byDay(data.releases)[day];
  if (!games) return;
  openModal(html`
    ${modalHeader(formatDate(day))}
    <div class="cal-games cal-day-games">${[...games].sort(byRelease).map((g) => card(g, true))}</div>`);
}

function draw() {
  const days = byDay(data.releases);
  const today = new Date();
  const todayKey = monthOf(today) === shown ? `${shown}-${String(today.getDate()).padStart(2, '0')}` : null;
  mount(main.querySelector('#calBody'), html`
    <div class="cal-layout">
      <div class="cal-side">
        <div class="cal-nav">
          <button class="pf-btn" type="button" data-step="-1" aria-label="Mes anterior">‹</button>
          <div class="cal-title">
            <h2 class="cal-month">${monthLabel(shown)}</h2>
            ${shown !== current ? html`<button class="pf-btn cal-today" type="button" data-today>Hoy</button>` : ''}
          </div>
          <button class="pf-btn" type="button" data-step="1" aria-label="Mes siguiente">›</button>
        </div>
        <div class="cal-grid" role="grid" aria-label="${monthLabel(shown)}">
          ${WEEKDAYS.map((d) => html`<div class="cal-weekday" aria-hidden="true">${d}</div>`)}
          ${monthWeeks(shown).flat().map((day) => cell(day, day && days[day], todayKey))}
        </div>
      </div>
      <div class="cal-list">
        <h2 class="cal-list-title">Juegos del mes</h2>
        ${data.releases.length
          ? html`<div class="cal-games" id="calMonth">${[...data.releases].sort(byRelease).map((g) => card(g))}</div>`
          : html`<div class="cal-empty">Ningún lanzamiento este mes.</div>`}
      </div>
    </div>
    ${data.undated.length
      ? html`
        <div class="section-header"><h2 class="section-title">Sin fecha confirmada</h2><div class="section-line"></div></div>
        <div class="gc-grid" id="calUndated">${data.undated.map(card)}</div>`
      : ''}`);
}

async function load(month) {
  const mine = ++navigation;
  try {
    const answer = await api(`/group/releases?month=${month}`);
    if (!answer || mine !== navigation) return;
    shown = month;
    data = answer;
    draw();
  } catch (err) {
    if (mine === navigation) mount(main.querySelector('#calBody'), html`<div class="pf-empty">Error cargando el calendario: ${err.message}</div>`);
  }
}

export async function render(ctx) {
  main = ctx.main;
  current = monthOf(new Date());
  shown = current;
  mount(main, html`
    <h1 class="pf-title pg-title">Calendario de lanzamientos</h1>
    <p class="pf-sub cal-intro">Los lanzamientos de todos los juegos del catálogo, los quiera alguien o no.</p>
    <div id="calBody"><div class="loading-spinner">Cargando el calendario...</div></div>`);
  main.querySelector('#calBody').addEventListener('click', (e) => {
    if (e.target.closest('[data-today]')) {
      load(current);
      return;
    }
    const step = e.target.closest('[data-step]');
    if (step) {
      const month = shiftMonth(shown, Number(step.dataset.step));
      load(month);
      return;
    }
    const day = e.target.closest('[data-day]');
    if (day) openDay(day.dataset.day);
  });
  await load(current);
}
