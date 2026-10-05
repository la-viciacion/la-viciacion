// API client (FastAPI + JWT) and session token storage.

export const API_BASE = '/api/v1';

const TOKEN_KEY = 'lv_token';

export const session = {
  getToken: () => localStorage.getItem(TOKEN_KEY),
  setToken: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized = () => {};

/** Called when the API answers 401 (the router shows the login page). */
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

export const jsonRequest = (method, body) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

// detail can be a string, an object ({message, counts}) or a 422 list of issues
function errorMessage(detail, status) {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ');
  return detail?.message || `HTTP ${status}`;
}

export async function api(path, options = {}) {
  const headers = { ...options.headers };
  const token = session.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    session.clear();
    onUnauthorized();
    return null;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Error desconocido' }));
    const error = new Error(errorMessage(body.detail, res.status));
    error.status = res.status;
    error.detail = body.detail;
    throw error;
  }

  const type = res.headers.get('content-type') || '';
  if (type.includes('application/json')) return res.json();
  if (type.includes('image/') || type.includes('application/gzip')) return res.blob();
  return res.text();
}

/** OAuth2PasswordRequestForm wants application/x-www-form-urlencoded. */
export async function login(username, password) {
  const res = await fetch(`${API_BASE}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Usuario o contraseña incorrectos');
  }
  const data = await res.json();
  session.setToken(data.access_token);
}

/** Object URL of the user's avatar, or null when they have none. */
export async function loadAvatarUrl(username) {
  const blob = await api(`/users/${encodeURIComponent(username)}/avatar`).catch(() => null);
  return blob instanceof Blob && blob.size ? URL.createObjectURL(blob) : null;
}
