// A <select> that searches. The select stays the field of the form (its name, its value, its options, its `change` event) and is
// hidden; this draws one text box in its place. It shows the chosen option, opens all of them as a list when it is focused and
// filters them as the person types (on the text and on the value, so `flash` finds `google/gemini-2.5-flash`). Built with DOM
// calls, never with markup strings: what is in the options is data (a provider's model names).
const instances = new WeakMap();

const entriesOf = (select) => [...select.children].flatMap((node) => (node.tagName === 'OPTGROUP'
  ? [{ group: node.label }, ...[...node.children].map((o) => ({ value: o.value, text: o.textContent }))]
  : [{ value: node.value, text: node.textContent }]));

/** Makes `select` searchable and returns `{ refresh }`, which redraws the box after the options or the value changed from outside. */
export function searchable(select) {
  if (instances.has(select)) return instances.get(select);

  const root = document.createElement('div');
  root.className = 'adm-combo';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'adm-input adm-combo-input';
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.placeholder = 'Buscar…';
  const list = document.createElement('ul');
  list.className = 'adm-combo-list';
  list.setAttribute('role', 'listbox');
  list.hidden = true;
  root.append(input, list);
  select.before(root);
  select.hidden = true;

  let query = '';
  let shown = []; // the options on the list, without the group headers
  let active = -1;
  const isOpen = () => !list.hidden;
  const chosenText = () => select.selectedOptions[0]?.textContent ?? '';

  function render() {
    const wanted = query.trim().toLowerCase();
    const matches = (e) => !wanted || e.value.toLowerCase().includes(wanted) || e.text.toLowerCase().includes(wanted);
    const rows = [];
    let header = null;
    shown = [];
    for (const entry of entriesOf(select)) {
      if ('group' in entry) { header = entry; continue; }
      if (!matches(entry)) continue;
      if (header) { rows.push(header); header = null; } // a vendor's title only when one of its models is on the list
      rows.push(entry);
      shown.push(entry);
    }
    list.replaceChildren();
    for (const row of rows) {
      const item = document.createElement('li');
      if ('group' in row) {
        item.className = 'adm-combo-group';
        item.textContent = row.group;
        item.setAttribute('role', 'presentation');
      } else {
        item.className = 'adm-combo-item';
        item.setAttribute('role', 'option');
        item.dataset.value = row.value;
        item.textContent = row.text;
        item.setAttribute('aria-selected', String(row.value === select.value));
      }
      list.append(item);
    }
    if (!shown.length) {
      const none = document.createElement('li');
      none.className = 'adm-combo-empty';
      none.textContent = 'Ningún modelo coincide';
      list.append(none);
    }
    mark(Math.min(Math.max(active, 0), shown.length - 1));
  }

  // The highlighted option (the one Enter picks): moved with the arrows and by what is typed.
  function mark(index) {
    active = index;
    const items = [...list.querySelectorAll('.adm-combo-item')];
    items.forEach((item, i) => item.classList.toggle('active', i === index));
    items[index]?.scrollIntoView?.({ block: 'nearest' });
  }

  function open() {
    if (isOpen() || input.disabled) return;
    query = '';
    active = Math.max(entriesOf(select).filter((e) => !('group' in e)).findIndex((e) => e.value === select.value), 0);
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    render();
    input.select();
  }

  function close() {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.value = chosenText(); // what was typed and not picked is dropped: the field never holds a half-written name
  }

  function choose(value) {
    if (select.value !== value) {
      select.value = value;
      select.dispatchEvent(new select.ownerDocument.defaultView.Event('change', { bubbles: true }));
    }
    close();
  }

  input.addEventListener('focus', open);
  input.addEventListener('click', open);
  input.addEventListener('blur', close);
  input.addEventListener('input', () => {
    if (!isOpen()) open();
    query = input.value;
    active = 0;
    render();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen()) return open();
      if (shown.length) mark((active + (e.key === 'ArrowDown' ? 1 : -1) + shown.length) % shown.length);
    } else if (e.key === 'Enter') {
      e.preventDefault(); // it must not save the page's form
      if (isOpen() && shown[active]) choose(shown[active].value);
    } else if (e.key === 'Escape' && isOpen()) {
      e.preventDefault();
      close();
    }
  });
  // Keep the focus in the box while the list is used, and pick on click. Inside a <label> a click would also click the box again:
  list.addEventListener('mousedown', (e) => e.preventDefault());
  list.addEventListener('click', (e) => {
    e.preventDefault();
    const item = e.target.closest('.adm-combo-item');
    if (item) choose(item.dataset.value);
  });

  const api = {
    refresh() {
      input.disabled = select.disabled;
      if (isOpen()) render();
      else input.value = chosenText();
    },
  };
  instances.set(select, api);
  api.refresh();
  return api;
}
