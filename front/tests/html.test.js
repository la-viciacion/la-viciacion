import assert from 'node:assert/strict';
import { test } from 'node:test';
import { escapeHtml, html, mount, raw } from '../js/lib/html.js';

test('escapes interpolated values', () => {
  const evil = '<img src=x onerror="alert(1)">';
  assert.equal(String(html`<p>${evil}</p>`), '<p>&lt;img src=x onerror=&quot;alert(1)&quot;&gt;</p>');
});

test('escapes quotes so values are safe inside attributes', () => {
  assert.equal(String(html`<a title="${'" onclick="x'}">`), '<a title="&quot; onclick=&quot;x">');
  assert.equal(escapeHtml("it's"), 'it&#39;s');
});

test('nested templates and arrays of templates are not double-escaped', () => {
  const items = ['a', '<b>'].map((x) => html`<li>${x}</li>`);
  assert.equal(String(html`<ul>${items}</ul>`), '<ul><li>a</li><li>&lt;b&gt;</li></ul>');
});

test('plain strings inside an array are escaped', () => {
  assert.equal(String(html`${['<', '>']}`), '&lt;&gt;');
});

test('false, true, null and undefined render as nothing; 0 renders', () => {
  assert.equal(String(html`[${false}${true}${null}${undefined}]`), '[]');
  assert.equal(String(html`[${0}]`), '[0]');
});

test('raw() marks trusted markup', () => {
  assert.equal(String(html`${raw('&times;')}`), '&times;');
});

test('mount refuses plain strings', () => {
  assert.throws(() => mount({}, '<b>x</b>'), TypeError);
});
