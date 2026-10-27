// What the AI has cost (admin panel, Sistema → Uso de IA): the figures of one month or of everything. Pure, so it can be tested.
// `data` is GET /manage/ai-usage: { currency, total, items, months: [{ month, total, items }], days: [{ date, total }] }.

export const ALL = 'all';

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

/** 0.0123 -> "0,0123 US$", 0.6 -> "0,60 US$": the model of a notice costs a fraction of a cent, so up to 4 decimals show. */
export function money(value, currency = 'usd') {
  return value.toLocaleString('es-ES', { style: 'currency', currency: currency.toUpperCase(), minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

/** "2026-09" -> "Septiembre de 2026". */
export function monthLabel(month) {
  const text = `${MONTHS[Number(month.slice(5)) - 1]} de ${month.slice(0, 4)}`;
  return text[0].toUpperCase() + text.slice(1);
}

/** The months on offer, the latest first (the ones with some spend). */
export const monthChoices = (data) => data.months.map((m) => m.month).reverse();

/** The figures of a month, or of everything with ALL: { total, items, days (the month's, oldest first; none for ALL) }.
 * A month that is not in the data costs nothing. */
export function selection(data, month) {
  if (month === ALL) return { total: data.total, items: data.items, days: [] };
  const found = data.months.find((m) => m.month === month);
  return {
    total: found ? found.total : 0,
    items: found ? found.items : [],
    days: data.days.filter((d) => d.date.startsWith(month)),
  };
}

/** How much of `max` a figure is, as a percentage for a bar (0 when there is nothing to compare with). */
export const share = (value, max) => (max > 0 ? Math.round((value / max) * 100) : 0);
