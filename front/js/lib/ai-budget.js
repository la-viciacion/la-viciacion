// The monthly budget of the group's AI key (see api/src/utils/ai_budget.py), as the admin's panel and the player's screen show it.
// Pure, so it can be tested. A cap is whole dollars a month; no cap (null) is no limit and 0 is nothing of the group's key.
import { money } from './ai-usage.js';

/** "sin límite" for no cap, "sin IA del grupo" for 0, else "5,00 US$". */
export const capLabel = (cap) => (cap == null ? 'sin límite' : cap === 0 ? 'sin IA del grupo' : money(cap));

/** How much of a cap is spent, as a percentage for a bar (0 without a cap), never over 100. */
export const spentShare = (spent, cap) => (cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : 0);

/** Whether a budget is spent (it has a cap and the spending reached it). */
export const isSpent = (spent, cap) => cap > 0 && spent >= cap;

/** Whether a budget is close to spent (80 % or more, and not spent yet). */
export const isNearly = (spent, cap) => cap > 0 && !isSpent(spent, cap) && spent / cap >= 0.8;

/** What an admin typed in the budget box: '' is the default (null), a whole number from 0 to 10000 is a cap, anything else NaN. */
export function parseCap(text) {
  const value = String(text).trim();
  if (value === '') return null;
  if (!/^\d{1,5}$/.test(value)) return NaN;
  const cap = Number(value);
  return cap <= 10000 ? cap : NaN;
}

/** One line for a budget: what is spent of what, and when it starts again. */
export function budgetLine(label, budget, resetsOn) {
  if (budget.cap == null) return `${label}: sin límite.`;
  if (budget.cap === 0) return `${label}: sin IA de la clave del grupo.`;
  const again = resetsOn ? ` Se renueva el ${new Date(`${resetsOn}T00:00:00`).toLocaleDateString('es-ES', { day: 'numeric', month: 'long' })}.` : '';
  return `${label}: ${money(budget.spent)} de ${money(budget.cap)}.${again}`;
}
