// Status line under a form or button (`.pf-msg`): green when `ok`, red otherwise, hidden when empty.
export function flash(el, message, ok = false) {
  el.textContent = message;
  el.className = `pf-msg ${message ? (ok ? 'ok' : 'err') : ''}`;
}
