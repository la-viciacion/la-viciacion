// The wallet of the group's AI key (see api/src/utils/ai_wallet.py), as the admin's panel and the player's screen show it.
// Pure, so it can be tested. Amounts are dollars; a balance of 0 or less is nothing left.
import { money } from './ai-usage.js';

export const WALLET_MAX = 10000;

/** What an admin typed as an amount: dollars with up to two decimals (a comma or a point), negative for a refund. NaN if it is not one, or is 0. */
export function parseAmount(text) {
  const value = String(text).trim().replace(',', '.');
  if (!/^-?\d{1,5}(\.\d{1,2})?$/.test(value)) return NaN;
  const amount = Number(value);
  return amount !== 0 && Math.abs(amount) <= WALLET_MAX ? amount : NaN;
}

/** Whether a balance is spent: nothing left, or in debt (the cost of a call is known only when it ends). */
export const isEmpty = (balance) => balance <= 0;

/** What the OpenAI account holds beyond what the wallets say is available (negative: the account holds less). Rounded to the cent. */
export const gap = (openai, available) => Math.round((openai - available) * 100) / 100 || 0; // || 0: never -0

/** The line of the player's own screen, or '' while the wallet is off. */
export function walletLine(wallet) {
  if (!wallet) return '';
  const left = isEmpty(wallet.balance) ? `Tu saldo de IA del grupo está agotado (${money(wallet.balance)}).` : `Tu saldo de IA del grupo: ${money(wallet.balance)}.`;
  return `${left} Has aportado ${money(wallet.contributed)} y has gastado ${money(wallet.spent)}.`;
}
