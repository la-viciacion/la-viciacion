// The period of a group challenge, as the form of the admin and the players' proposals both ask for it: a month, a week or
// free dates, each showing only what it needs; with `repeatable`, a month may also repeat every month. `periodField()` is the markup, `bindPeriod(box)` makes it show and hide and
// `readPeriod(box)` gives what the API takes (`periodOptions`).
import { PERIOD_MODES, chosenPeriodLine, launchMonths, nextMonday, periodOptions, todayIso } from '../lib/challenges.js';
import { html } from '../lib/html.js';

export function periodField({ repeatable = false } = {}) {
  const first = todayIso();
  return html`
    <div class="adm-period" data-period-field>
      <label>Periodo<select class="adm-input" data-period>
        ${PERIOD_MODES.map(([value, label]) => html`<option value="${value}">${label}</option>`)}
      </select></label>
      <label data-period-for="month" data-period-unless-repeat>Mes<select class="adm-input" data-period-month>
        ${launchMonths().map((m) => html`<option value="${m.value}">${m.label}</option>`)}
      </select></label>
      ${repeatable ? html`
        <label class="adm-check" data-period-for="month"><input type="checkbox" data-period-repeat /> Repetir cada mes (se lanza solo el día 1)</label>
        <label class="adm-check" data-period-for="month" data-period-when-repeat hidden><input type="checkbox" data-period-now /> Lanzar ya el de este mes (si no, empieza el mes que viene)</label>` : ''}
      <label data-period-for="week" hidden>Primer día (dura siete)<input class="adm-input" type="date" data-period-week min="${first}" value="${nextMonday()}" /></label>
      <label data-period-for="range" hidden>Desde<input class="adm-input" type="date" data-period-from min="${first}" /></label>
      <label data-period-for="range" hidden>Hasta<input class="adm-input" type="date" data-period-to min="${first}" /></label>
    </div>`;
}

/** What the form is asked for: "month", "week", "range" or, for a month that repeats, "repeat". */
export function periodMode(box) {
  const mode = box.querySelector('[data-period]').value;
  return mode === 'month' && box.querySelector('[data-period-repeat]')?.checked ? 'repeat' : mode;
}

export function bindPeriod(box) {
  const show = () => {
    const mode = periodMode(box);
    const shown = mode === 'repeat' ? 'month' : mode;
    box.querySelectorAll('[data-period-for]').forEach((el) => {
      el.hidden = el.dataset.periodFor !== shown || (mode === 'repeat' ? 'periodUnlessRepeat' in el.dataset : 'periodWhenRepeat' in el.dataset);
    });
  };
  box.addEventListener('change', show);
  show();
}

function chosen(box) {
  const value = (selector) => box.querySelector(selector).value;
  return {
    period: value('[data-period]'), month: value('[data-period-month]'), week: value('[data-period-week]'),
    from: value('[data-period-from]'), to: value('[data-period-to]'),
    repeat: box.querySelector('[data-period-repeat]')?.checked, now: box.querySelector('[data-period-now]')?.checked,
  };
}

/** The period as a sentence, for a summary. */
export function describePeriod(box) {
  return chosenPeriodLine({ ...chosen(box), monthLabel: box.querySelector('[data-period-month]').selectedOptions[0]?.textContent.trim() });
}

export function readPeriod(box) {
  return periodOptions(chosen(box));
}
