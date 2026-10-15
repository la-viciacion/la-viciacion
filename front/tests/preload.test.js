import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const IMPORT = /^\s*(?:import|export)\s[^'"]*?from\s+['"](\.[^'"]+)['"]|^\s*import\s+['"](\.[^'"]+)['"]/gm;

/** Every module main.js loads before the first screen: its static imports and theirs (not the pages it imports
 * on demand with import()). */
function startupModules() {
  const seen = new Set();
  const walk = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    for (const [, from, bare] of readFileSync(join(ROOT, file), 'utf8').matchAll(IMPORT)) {
      walk(relative(ROOT, join(ROOT, dirname(file), from || bare)).replaceAll('\\', '/'));
    }
  };
  walk('js/main.js');
  seen.delete('js/main.js'); // the <script> tag itself
  return [...seen].sort();
}

const preloaded = () => [...readFileSync(join(ROOT, 'index.html'), 'utf8').matchAll(/<link rel="modulepreload" href="([^"]+)"/g)]
  .map(([, href]) => href)
  .sort();

test('index.html preloads exactly the modules of the first screen', () => {
  // without the list the browser finds the imports one level at a time, a round trip per level; a module that is
  // added or dropped from main.js's imports has to be added or dropped here too
  assert.deepEqual(preloaded(), startupModules());
});
