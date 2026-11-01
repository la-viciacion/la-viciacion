// The period of a group challenge, as the form of the admin and the players' proposals both ask for it: a month, a week or
// free dates, each showing only what it needs. `periodField()` is the markup, `bindPeriod(box)` makes it show and hide and
// `readPeriod(box)` gives what the API takes (`periodOptions`).
import { PERIOD_MODES, launchMonths, nextMonday, periodOptions, todayIso } from '../lib/challenges.js';
import { html } from '../lib/html.js';

export function periodField() {
  const first = todayIso();
  return html`
    <div class="adm-period" data-period-field>
      <label>Periodo<select class="adm-input" data-period>
        ${PERIOD_MODES.map(([value, label]) => html`<option value="${value}">${label}</option>`)}
      </select></label>
      <label data-period-for="month">Mes<select class="adm-input" data-period-month>
        ${launchMonths().map((m) => html`<option value="${m.value}">${m.label}</option>`)}
      </select></label>
      <label data-period-for="week" hidden>Primer día (dura siete)<input class="adm-input" type="date" data-period-week min="${first}" value="${nextMonday()}" /></label>
      <label data-period-for="range" hidden>Desde<input class="adm-input" type="date" data-period-from min="${first}" /></label>
      <label data-period-for="range" hidden>Hasta<input class="adm-input" type="date" data-period-to min="${first}" /></label>
    </div>`;
}

export function bindPeriod(box) {
  const show = () => {
    const mode = box.querySelector('[data-period]').value;
    box.querySelectorAll('[data-period-for]').forEach((el) => { el.hidden = el.dataset.periodFor !== mode; });
  };
  box.addEventListener('change', show);
  show();
}

export function readPeriod(box) {
  const value = (selector) => box.querySelector(selector).value;
  return periodOptions({
    period: value('[data-period]'), month: value('[data-period-month]'), week: value('[data-period-week]'),
    from: value('[data-period-from]'), to: value('[data-period-to]'),
  });
}
