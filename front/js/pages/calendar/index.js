// Release calendar (#/calendar): the games the group is waiting for, by day, from every player's wishlist (not only
// yours). GET /group/releases?month=YYYY-MM; from the running month on, since what is out is not a release any more.
// A day with one game links to its page; a day with several opens a list. The games with no confirmed date are listed apart. Nothing is stored here: the wishes are the only data.
import { api } from '../../lib/api.js';
import { byDay, monthLabel, monthOf, monthWeeks, shiftMonth, waiting } from '../../lib/calendar.js';
import { formatDate, parseDay } from '../../lib/format.js';
import { html, mount } from '../../lib/html.js';
import { gameHref } from '../../lib/links.js';
import { countdown } from '../../lib/wishlist.js';

export const active = null; // it belongs to no item of the top bar

const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

let main;
let current; // the running month, "YYYY-MM"
let shown; // the month on screen
let data = null; // the answer for `shown`
let picked = null; // the day selected, "YYYY-MM-DD"
let navigation = 0; // only the latest request may draw

const card = (g) => html`
  <a class="gc-card cal-game" href="${gameHref(g.id)}">
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
  const classes = ['cal-cell', games ? 'has' : '', day === today ? 'today' : '', day === picked ? 'picked' : ''].filter(Boolean).join(' ');
  const number = Number(day.slice(8));
  if (!games) return html`<div class="${classes}"><span class="cal-day">${number}</span></div>`;
  const label = `${number}: ${games.map((g) => g.name).join(', ')}`;
  const thumb = games[0].image_url ? html`<img class="cal-thumb" src="${games[0].image_url}" alt="" loading="lazy" />` : '';
  // a day with one game goes straight to its page; with several, the day opens and its games are listed below
  if (games.length === 1) {
    return html`
      <a class="${classes}" href="${gameHref(games[0].id)}" title="${[games[0].name, waiting(games[0].wanted_by)].filter(Boolean).join(' · ')}" aria-label="${label}">
        <span class="cal-day">${number}</span>
        ${thumb}
        <span class="cal-count">${games[0].name}</span>
      </a>`;
  }
  return html`
    <button class="${classes}" type="button" data-day="${day}" aria-pressed="${String(day === picked)}" aria-label="${label}">
      <span class="cal-day">${number}</span>
      ${thumb}
      <span class="cal-count">${games.length} juegos</span>
    </button>`;
}

function draw() {
  const days = byDay(data.releases);
  const today = new Date();
  const todayKey = monthOf(today) === shown ? `${shown}-${String(today.getDate()).padStart(2, '0')}` : null;
  const chosen = picked && days[picked] ? days[picked] : null;
  mount(main.querySelector('#calBody'), html`
    <div class="cal-nav">
      <button class="pf-btn" type="button" data-step="-1" aria-label="Mes anterior" ${shown <= current ? html`disabled` : ''}>‹</button>
      <h2 class="cal-month">${monthLabel(shown)}</h2>
      <button class="pf-btn" type="button" data-step="1" aria-label="Mes siguiente">›</button>
    </div>
    <div class="cal-grid" role="grid" aria-label="${monthLabel(shown)}">
      ${WEEKDAYS.map((d) => html`<div class="cal-weekday" aria-hidden="true">${d}</div>`)}
      ${monthWeeks(shown).flat().map((day) => cell(day, day && days[day], todayKey))}
    </div>
    ${data.releases.length ? '' : html`<div class="pf-empty cal-empty">Ningún lanzamiento deseado este mes.</div>`}
    ${chosen
      ? html`
        <div class="section-header"><h2 class="section-title">${parseDay(picked).toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}</h2><div class="section-line"></div></div>
        <div class="gc-grid" id="calDay">${chosen.map(card)}</div>`
      : ''}
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
    // the first day with several games is selected, so the page opens on a list (a day with one game is a link)
    const days = byDay(data.releases);
    if (!picked || !picked.startsWith(month) || days[picked]?.length < 2) {
      picked = Object.keys(days).find((day) => days[day].length > 1) ?? null;
    }
    draw();
  } catch (err) {
    if (mine === navigation) mount(main.querySelector('#calBody'), html`<div class="pf-empty">Error cargando el calendario: ${err.message}</div>`);
  }
}

export async function render(ctx) {
  main = ctx.main;
  current = monthOf(new Date());
  shown = current;
  picked = null;
  mount(main, html`
    <h1 class="pf-title pg-title">Calendario de lanzamientos</h1>
    <p class="pf-sub cal-intro">Los juegos que está esperando el grupo, de las listas de deseados de todos.</p>
    <div id="calBody"><div class="loading-spinner">Cargando el calendario...</div></div>`);
  main.querySelector('#calBody').addEventListener('click', (e) => {
    const step = e.target.closest('[data-step]');
    if (step) {
      const month = shiftMonth(shown, Number(step.dataset.step));
      if (month >= current) load(month);
      return;
    }
    const day = e.target.closest('[data-day]');
    if (day) {
      picked = day.dataset.day;
      draw();
    }
  });
  await load(current);
}
