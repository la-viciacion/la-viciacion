import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const css = readFileSync(new URL('../css/admin.css', import.meta.url), 'utf8');

// `.adm-ai-prompt` is indented 48px to sit under the text of a notice, which hangs from a switch. The chat's and the guide's cards have
// no such layout: their Instrucciones button was shifted to the right until the indent was taken off there.
test('the instructions of the chat and of the guide are not indented like those of a notice', () => {
  assert.match(css, /\.adm-ai-prompt \{ margin: 0 0 0 48px; \}/, 'the notices keep their indent');
  const rule = css.match(/([^{}]*\.adm-ai-prompt[^{}]*)\{\s*margin-left:\s*0;\s*\}/);
  assert.ok(rule, 'a rule that takes the indent off');
  assert.match(rule[1], /\.adm-chat-card \.adm-ai-prompt/);
  assert.match(rule[1], /\.adm-guide-card \.adm-ai-prompt/);
});
