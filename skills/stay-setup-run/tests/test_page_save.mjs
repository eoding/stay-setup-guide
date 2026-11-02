import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { JSDOM } = require('jsdom');
const source = readFileSync(new URL('../scripts/stay_helper.js', import.meta.url), 'utf8');

function screen() {
  const dom = new JSDOM(`<div class="right_header"><button id="save">저장</button></div>
    <form id="default"><input id="master_id" type="hidden" value="123"></form>`,
    { url: 'https://example.test/stay/123/', runScripts: 'outside-only', pretendToBeVisual: true });
  const w = dom.window;
  w.fetch = (url, init = {}) => new Promise(resolve => w.setTimeout(() =>
    resolve({ status: init.testStatus || 200 }), init.testDelay || 20));
  w.eval(source);
  w.stayRun.config({ waitMs: 1200 });
  return { w, button: w.document.getElementById('save'), close: () => w.close() };
}

function toast(w) {
  const container = w.document.createElement('div');
  container.id = 'toast-container';
  container.innerHTML = '<div class="toast">저장되었습니다.</div>';
  w.document.body.appendChild(container);
}

test('background htmx swaps do not prove that the page form was saved', async () => {
  const s = screen();
  try {
    s.button.onclick = () => s.w.setTimeout(() =>
      s.w.document.dispatchEvent(new s.w.CustomEvent('htmx:after:swap')), 20);
    const result = await s.w.stayRun.pageSave();
    assert.equal(result.saved, false);
    assert.equal(result.status, 'timeout');
  } finally { s.close(); }
});

test('the target POST remains visible after background requests finish or remain pending', async () => {
  const s = screen();
  try {
    s.button.onclick = () => {
      s.w.fetch('/fit/master/123/change/', { method: 'POST', testDelay: 20 });
      s.w.fetch('/notifications/unread-count/', { testDelay: 25 });
      s.w.fetch('/common/slow-poll/', { testDelay: 3000 });
    };
    const result = await s.w.stayRun.pageSave();
    assert.equal(result.saved, true);
    assert.equal(result.status, 'settled');
    assert.equal(result.xhr.url, '/fit/master/123/change/');
  } finally { s.close(); }
});

test('a GET of the form URL cannot confirm a save', async () => {
  const s = screen();
  try {
    s.button.onclick = () => s.w.fetch('/fit/master/123/change/');
    assert.equal((await s.w.stayRun.pageSave()).saved, false);
  } finally { s.close(); }
});

test('another hotel POST cannot confirm this hotel save', async () => {
  const s = screen();
  try {
    s.button.onclick = () => s.w.fetch('/fit/master/456/change/', { method: 'POST' });
    assert.equal((await s.w.stayRun.pageSave()).saved, false);
  } finally { s.close(); }
});

test('a new success toast without a target write is insufficient', async () => {
  const s = screen();
  try {
    s.button.onclick = () => toast(s.w);
    assert.equal((await s.w.stayRun.pageSave()).saved, false);
  } finally { s.close(); }
});

test('a background success toast cannot override the failed target write', async () => {
  const s = screen();
  try {
    s.button.onclick = () => {
      s.w.fetch('/fit/master/123/change/', { method: 'POST', testStatus: 500 });
      toast(s.w);
    };
    const result = await s.w.stayRun.pageSave();
    assert.equal(result.saved, false);
    assert.equal(result.status, 'error');
  } finally { s.close(); }
});

test('a pre-existing request and its toast cannot confirm this click', async () => {
  const s = screen();
  try {
    s.w.fetch('/fit/master/123/change/', { method: 'POST', testDelay: 30 }).then(() => toast(s.w));
    s.button.onclick = () => {};
    assert.equal((await s.w.stayRun.pageSave()).saved, false);
  } finally { s.close(); }
});

test('a login page never returns saved true', async () => {
  const s = screen();
  try {
    s.button.onclick = () => s.w.fetch('/fit/master/123/change/', { method: 'POST' }).then(() => {
      const password = s.w.document.createElement('input');
      password.type = 'password';
      s.w.document.body.appendChild(password);
    });
    const result = await s.w.stayRun.pageSave();
    assert.equal(result.status, 'login');
    assert.equal(result.saved, false);
  } finally { s.close(); }
});

test('the ordinary submit entry used by basic-information steps confirms the page POST', async () => {
  const s = screen();
  try {
    s.button.onclick = () => s.w.fetch('/fit/master/123/change/', { method: 'POST' }).then(() => toast(s.w));
    const result = await s.w.stayRun.submit('저장');
    assert.equal(result.status, 'settled');
    assert.equal(result.saved, true);
  } finally { s.close(); }
});
