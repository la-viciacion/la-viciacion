// The admin pages must open with what the real API answers (tests/fixtures/ are built by api/tests/front_fixtures.py from the
// route itself), not with an answer written by hand: a setting the API drops, or a field it renames, breaks a page here.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { installApi, installDom, installStorage, settle } from './dom.js';

installStorage();
const window = installDom('<div id="panel"></div>', 'http://localhost/');
globalThis.location = window.location;
const { render: renderSettings } = await import('../js/pages/admin/settings.js');
const { render: renderHome } = await import('../js/pages/admin/home.js');
const { ENTITIES } = await import('../js/pages/admin/entities.js');

const fixture = (name) => JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), 'utf8'));
const SCENARIOS = { 'both providers set up': 'manage-settings.full.json', 'an .env without any AI': 'manage-settings.empty.json' };
const panel = () => document.getElementById('panel');
const MODELS = { provider: 'openai', models: ['gpt-test'], defaults: {} };
const PAGES = Object.entries(ENTITIES).filter(([, entity]) => entity.custom === 'settings');

for (const [scenario, file] of Object.entries(SCENARIOS)) {
  for (const [tab, entity] of PAGES) {
    test(`the "${tab}" page opens with the real answer of the API: ${scenario}`, async () => {
      installApi({ 'GET /manage/settings/ai-models': MODELS, 'GET /manage/ai-usage/budgets': { month: '2026-11', resets_on: '2026-12-01', group: { cap: 0, spent: 0 }, unpriced: { calls: 0, models: [] }, default_user_cap: 0, players: [] }, 'GET /manage/settings': fixture(file) });
      await renderSettings(panel(), { entity });
      await settle();
      assert.equal(panel().querySelector(".empty-state"), null, panel().querySelector(".empty-state")?.textContent); // an error state is how a page says it failed
      assert.ok(panel().querySelector('.adm-set-card'));
    });
  }

  test(`the home opens with the real answer of the API: ${scenario}`, async () => {
    installApi({
      'GET /manage/overview': { users: 1, games: 2, timers: 3, active_timers: 0, library: 4 },
      'GET /manage/attention': { stale_timer_hours: 12, stale_timers: 0, stale_timers_oldest: [], users_without_telegram: 0, games_without_source: 0, pending_challenge_proposals: 0 },
      'GET /manage/settings': fixture(file),
    });
    await renderHome(panel(), { admin: { jumpTo() {}, open() {} } });
    await settle();
    assert.equal(panel().querySelector('.empty-state'), null, panel().textContent.slice(0, 200));
    assert.match(panel().textContent, /Inteligencia artificial/);
  });
}
