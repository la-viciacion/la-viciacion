// Tagged template that escapes every interpolated value by default.
//
//   mount(el, html`<p title="${title}">${name}</p>`)
//
// Values are escaped unless they are the result of another html`` (nested
// templates, arrays of them) or wrapped with raw(). false/null/undefined/true
// render as nothing, so `${cond && html`...`}` works.

class SafeHtml {
  constructor(value) {
    this.value = value;
  }

  toString() {
    return this.value;
  }
}

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function render(value) {
  if (value instanceof SafeHtml) return value.value;
  if (Array.isArray(value)) return value.map(render).join('');
  if (value === null || value === undefined || value === false || value === true) return '';
  return escapeHtml(value);
}

export function html(strings, ...values) {
  let out = strings[0];
  values.forEach((v, i) => {
    out += render(v) + strings[i + 1];
  });
  return new SafeHtml(out);
}

/** Mark a trusted string (static markup, an entity like &times;) as already safe. */
export const raw = (value) => new SafeHtml(String(value));

const assertSafe = (value) => {
  if (!(value instanceof SafeHtml)) throw new TypeError('Expected an html`` template, got a plain string');
};

/** Replace the content of an element. Refuses plain strings on purpose. */
export function mount(el, safe) {
  assertSafe(safe);
  el.innerHTML = safe.value;
  return el;
}

/** Append markup at the end of an element. */
export function append(el, safe) {
  assertSafe(safe);
  el.insertAdjacentHTML('beforeend', safe.value);
}
