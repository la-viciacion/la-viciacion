// What the page tests need from a browser: a DOM (jsdom), a localStorage and a fetch that answers from a table.
// Not a test file: each test imports it. `node --test` runs every file in its own process, so the globals set here
// never leak between files.
import { JSDOM } from 'jsdom';

/** A fresh document with `body` inside; `document` and `window` become globals, as the modules expect. */
export function installDom(body = '') {
  const dom = new JSDOM(`<!doctype html><html><body>${body}</body></html>`);
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  return dom.window;
}

export function installStorage() {
  const storage = new Map();
  globalThis.localStorage = {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key),
  };
}

export const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

/**
 * Replaces fetch. `routes` maps "METHOD /path-prefix" (the path after /api/v1) to a body or a function returning one;
 * the first key the request starts with wins, and a request nobody expects fails the test instead of reaching a network.
 * Returns the log of the requests made: [{ method, path, body }].
 */
export function installApi(routes) {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url).replace(/^\/api\/v1/, '');
    const method = options.method || 'GET';
    const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ method, path, body });
    const key = Object.keys(routes).find((k) => `${method} ${path}`.startsWith(k));
    if (!key) throw new Error(`unexpected request: ${method} ${path}`);
    const answer = typeof routes[key] === 'function' ? routes[key]({ method, path, body }) : routes[key];
    return answer instanceof Response ? answer : json(answer);
  };
  return calls;
}

/** Lets pending promises (a fetch, a render after it) finish. */
export const settle = () => new Promise((resolve) => setImmediate(resolve));

export const text = (selector, root = document) => [...root.querySelectorAll(selector)].map((el) => el.textContent.trim());
