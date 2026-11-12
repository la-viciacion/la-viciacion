// What the AI has cost (admin panel, IA → Uso y coste): the figures of one month or of everything. Pure, so it can be tested.
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

/** What OpenAI billed against what the app estimates its group key spent, month by month (the latest first): `billed` from
 * GET /manage/ai-usage, `calls` the months of GET /manage/ai-usage/calls (what the group's OpenAI key really cost). `difference` is billed minus estimated: positive is
 * spend the record does not explain (a call it never saw, a price that changed, something else on the account). */
export function reconcile(billed, calls) {
  const estimated = new Map(calls.map((m) => [m.month, m.group_openai_real_cost ?? 0]));
  const months = new Set([...billed.map((m) => m.month), ...estimated.keys()]);
  return [...months].sort().reverse().map((month) => {
    const spent = billed.find((m) => m.month === month)?.total ?? 0;
    const guess = estimated.get(month) ?? 0;
    return { month, billed: spent, estimated: guess, difference: Math.round((spent - guess) * 1e6) / 1e6 };
  });
}

/** How much of `max` a figure is, as a percentage for a bar (0 when there is nothing to compare with). */
export const share = (value, max) => (max > 0 ? Math.round((value / max) * 100) : 0);
