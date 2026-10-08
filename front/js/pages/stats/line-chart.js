// The line chart of the statistics page: the hours each player has added up, day by day. Plain SVG, no library.
import { hourAxis } from '../../lib/daily.js';
import { formatDate } from '../../lib/format.js';
import { html } from '../../lib/html.js';

const W = 640;
const H = 280;
const PAD = { left: 44, right: 14, top: 12, bottom: 28 };
const COLORS = ['--accent-teal', '--accent-gold', '--accent-purple', '--accent-pink', '--live-green', '--text-secondary'];

// past the last colour they repeat, dashed, so two players never look the same
const look = (i) => ({ color: `var(${COLORS[i % COLORS.length]})`, dash: i >= COLORS.length ? '6 4' : null });

/** `data` is what cumulativeSeries answers (at least two days). */
export function lineChart({ days, series }) {
  const axis = hourAxis(Math.max(...series.map((s) => s.values.at(-1))));
  const top = axis.top * 3600;
  const { ticks } = axis;
  const x = (i) => PAD.left + (i / (days.length - 1)) * (W - PAD.left - PAD.right);
  const y = (seconds) => PAD.top + (1 - seconds / top) * (H - PAD.top - PAD.bottom);
  const ranked = [...series].sort((a, b) => b.values.at(-1) - a.values.at(-1));
  return html`
    <svg class="st-line" viewBox="0 0 ${W} ${H}" role="img" aria-label="Horas acumuladas de cada jugador, día a día">
      ${ticks.map((h) => html`
        <line class="st-grid" x1="${PAD.left}" x2="${W - PAD.right}" y1="${y(h * 3600)}" y2="${y(h * 3600)}" />
        <text class="st-axis" x="${PAD.left - 6}" y="${y(h * 3600) + 4}" text-anchor="end">${h} h</text>`)}
      <text class="st-axis" x="${PAD.left}" y="${H - 8}" text-anchor="start">${formatDate(days[0])}</text>
      <text class="st-axis" x="${W - PAD.right}" y="${H - 8}" text-anchor="end">${formatDate(days.at(-1))}</text>
      ${ranked.map((s) => {
        const { color, dash } = look(series.indexOf(s));
        return html`<polyline class="st-path" style="stroke:${color}" ${dash ? html`stroke-dasharray="${dash}"` : ''}
          points="${s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')}"><title>${s.name}</title></polyline>`;
      })}
    </svg>
    <div class="st-legend">${ranked.map((s) => html`
      <span class="st-key"><i style="--c:${look(series.indexOf(s)).color}"></i>${s.name}${s.is_me ? ' (tú)' : ''}</span>`)}
    </div>`;
}
