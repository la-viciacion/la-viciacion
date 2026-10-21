import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ENTITY_OPTIONS, describe, detailParts } from '../js/pages/admin/audit-labels.js';

const entry = (over) => ({ method: 'PATCH', path: '/api/v1/manage/timers/12', entity: 'timers', entity_id: '12', detail: null, ...over });

test('a write on a row reads as verb, thing and number', () => {
  assert.equal(describe(entry()), 'Editó sesión #12');
  assert.equal(describe(entry({ method: 'DELETE' })), 'Borró sesión #12');
  assert.equal(describe(entry({ method: 'POST', entity: 'users', entity_id: '4', path: '/api/v1/manage/users' })), 'Creó usuario #4');
  assert.equal(describe(entry({ entity: 'user-achievements', entity_id: '7' })), 'Editó logro concedido #7');
});

test('the writes that are not on a row have their own sentence', () => {
  assert.equal(describe(entry({ method: 'PUT', entity: 'settings', entity_id: null, path: '/api/v1/manage/settings' })), 'Cambió los ajustes');
  assert.equal(describe(entry({ method: 'POST', entity: 'users', entity_id: '3', path: '/api/v1/manage/users/3/password' })), 'Cambió la contraseña de un usuario');
  assert.equal(describe(entry({ method: 'POST', entity: 'push', entity_id: null, path: '/api/v1/manage/push/announce' })), 'Envió un aviso en la app');
  assert.equal(describe(entry({ method: 'POST', entity: 'telegram', entity_id: null, path: '/api/v1/manage/telegram/announce' })), 'Envió un aviso por Telegram');
  assert.equal(describe(entry({ method: 'POST', entity: 'recalculate-achievements', entity_id: null, path: '/api/v1/manage/recalculate-achievements' })), 'Pidió recalcular todos los logros');
});

test('the AI running out of quota says which quota and who asked', () => {
  const quota = (detail) => entry({ method: 'SYSTEM', path: 'ai/chat', entity: 'ai', event: 'ai_quota', detail });
  assert.equal(describe(quota({ source: 'chat', kind: 'day' })), 'Se agotó el cupo de la IA por día al pedirlo el chat');
  assert.equal(describe(quota({ source: 'notice:new_game', kind: 'minute' })), 'Se agotó el cupo de la IA por minuto al pedirlo un aviso');
  assert.equal(describe(quota({ source: 'welcome', kind: 'unknown' })), 'Se agotó el cupo de la IA al pedirlo la bienvenida del grupo');
  assert.equal(describe(quota({ source: 'chat_test', kind: 'billing' })), 'Se agotó el cupo de la IA de facturación al pedirlo la prueba del chat');
  assert.equal(describe(quota(null)), 'Se agotó el cupo de la IA al pedirlo la IA');
  const parts = detailParts(quota({ source: 'chat', kind: 'day', quotas: ['GenerateRequestsPerDayPerProjectPerModel-FreeTier'], limit: '20', retry_after: 34 }));
  assert.match(parts.find(([title]) => title === 'Datos')[1], /"limit": "20"/);
});

test('an entity it does not know is still described', () => {
  assert.equal(describe(entry({ method: 'POST', entity: 'future', entity_id: null, path: '/api/v1/manage/future' })), 'Creó future');
});

test('the detail shows how it was, what was sent and the query, in that order', () => {
  const parts = detailParts(entry({ detail: { before: { notes: 'a' }, body: { notes: 'b' }, query: 'force=true' } }));
  assert.deepEqual(parts.map(([title]) => title), ['Antes', 'Enviado', 'Consulta']);
  assert.match(parts[0][1], /"notes": "a"/);
  assert.equal(parts[2][1], 'force=true');
});

test('no detail is nothing to show', () => {
  assert.deepEqual(detailParts(entry()), []);
});

test('the filter offers the sections that keep their rows, capitalised', () => {
  assert.deepEqual(ENTITY_OPTIONS[0], ['users', 'Usuario']);
  assert.ok(ENTITY_OPTIONS.some(([value]) => value === 'timers'));
});

test('a security event reads as a sentence, whatever its path', () => {
  const event = (name, over) => entry({ method: 'POST', path: '/api/v1/token', entity: 'auth', entity_id: null, event: name, username: 'ana', ...over });
  assert.equal(describe(event('login')), 'Inició sesión');
  assert.match(describe(event('login_failed', { detail: { locked: true } })), /bloqueada/);
  assert.equal(describe(event('login_failed')), 'Intento de acceso fallido');
  assert.match(describe(event('recovery_requested', { detail: { sent: true } })), /enlace enviado/);
  assert.equal(describe(event('profile_updated', { detail: { account: 'ana', changed: { email: {} } } })), 'Cambió el email');
  assert.equal(describe(event('profile_updated', { detail: { account: 'luis', changed: { email: {}, telegram_id: {} } } })), 'Cambió el email y el id de Telegram de luis');
  assert.equal(describe(event('something_new')), 'something_new');
});

test('an event shows its data and where it came from', () => {
  const parts = detailParts(entry({ event: 'login_failed', detail: { locked: true }, ip: '203.0.113.7', user_agent: 'Firefox' }));
  assert.deepEqual(parts.map(([title]) => title), ['Datos', 'Desde']);
  assert.equal(parts[1][1], '203.0.113.7 · Firefox');
});
