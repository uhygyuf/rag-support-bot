#!/usr/bin/env node
/* DOM-level unit tests for site/widget.js.

   The widget decides where to send a question at runtime:
     data-webhook > backend.json (hosted copy) > data-local-webhook (file:// only)
   These cases run the real file in a stubbed DOM and assert which URL it calls, what the visitor
   sees when the backend does not answer, and that an answer is rendered as text rather than HTML.
   No browser, no network.

   Run:  node tests/widget_dom_test.js        (exit 0 = all cases pass) */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.dirname(__dirname);
const SRC = fs.readFileSync(path.join(ROOT, 'site', 'widget.js'), 'utf8');
const LOCAL = 'http://127.0.0.1:5678/webhook/local-id/chat';

const results = [];
function record(name, ok, detail) {
  results.push({ case: name, status: ok ? 'PASS' : 'FAIL', detail: detail || '' });
  console.log((ok ? '  PASS ' : '  FAIL ') + name + (detail ? '  ' + detail : ''));
}

/* ---------- stubs ---------- */
function makeElement(tag) {
  const el = {
    tagName: tag, id: '', type: '', className: '', textContent: '', value: '',
    scrollTop: 0, scrollHeight: 0, style: {},
    children: [], listeners: {}, queries: {},
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); }
    },
    setAttribute() {}, focus() {},
    addEventListener(type, fn) { (el.listeners[type] = el.listeners[type] || []).push(fn); },
    appendChild(child) { el.children.push(child); return child; },
    querySelector(sel) { return (el.queries[sel] = el.queries[sel] || makeElement(sel)); }
  };
  Object.defineProperty(el, 'innerHTML', { set(v) { el._html = v; }, get() { return el._html || ''; } });
  return el;
}

function makeDom(opts) {
  const dom = {
    bodies: [], warns: [], fetches: [],
    currentScript: { getAttribute: (n) => (n in opts.attrs ? opts.attrs[n] : null) }
  };
  dom.document = {
    currentScript: dom.currentScript,
    head: makeElement('head'),
    body: { appendChild: (c) => { dom.bodies.push(c); return c; } },
    createElement: makeElement,
    addEventListener() {}
  };
  dom.warn = (...a) => dom.warns.push(a.map(String).join(' '));
  return dom;
}

function elementById(dom, id) { return dom.bodies.find((e) => e.id === id); }

/* ---------- one widget run ---------- */
function runWidget(dom, fetchImpl, sessionStorage) {
  const sandbox = {
    document: dom.document,
    location: dom.location,
    console: { warn: dom.warn, log: () => {} },
    fetch: fetchImpl,
    AbortController,
    setTimeout, clearTimeout,
    Math, JSON, Promise, Date, String, Object, Array, Error, RegExp, parseInt, isNaN
  };
  sandbox.window = sandbox;
  sandbox.sessionStorage = sessionStorage || { getItem: () => '1', setItem: () => {} };
  vm.createContext(sandbox);
  vm.runInContext(SRC, sandbox);
  return sandbox;
}

function ask(dom) {
  const panel = elementById(dom, 'rgw-panel');
  const input = panel.querySelector('#rgw-in');
  const form = panel.querySelector('form');
  input.value = 'How long does US shipping take?';
  form.listeners.submit[0]({ preventDefault() {} });
}

const tick = () => new Promise((r) => setTimeout(r, 25));

function lastBotMessage(dom) {
  const panel = elementById(dom, 'rgw-panel');
  const log = panel.querySelector('#rgw-log');
  const bot = log.children.filter((c) => String(c.className).indexOf('rgw-bot') !== -1);
  return bot.length ? bot[bot.length - 1].textContent : '(no message rendered)';
}

async function main() {
  console.log('='.repeat(74));
  console.log('WIDGET DOM TESTS: backend resolution, offline behaviour, hostile text');
  console.log('='.repeat(74));

  /* 1. page opened from disk (file://) must talk to the local n8n webhook */
  {
    const dom = makeDom({ attrs: { 'data-local-webhook': LOCAL } });
    dom.location = { protocol: 'file:', href: 'file:///E:/Hermes/Projects/rag-support-bot/site/index.html' };
    const calls = [];
    const sandbox = runWidget(dom, (url) => {
      calls.push(url);
      return Promise.resolve({ ok: true, text: () => Promise.resolve('{"output":"2-4 business days [faq.md]"}') });
    });
    await tick();
    ask(dom);
    await tick();
    record('file:// page calls the local webhook', calls.length === 1 && calls[0] === LOCAL,
      'calls: ' + JSON.stringify(calls));
    record('file:// page renders the answer', lastBotMessage(dom).indexOf('2-4 business days') !== -1,
      lastBotMessage(dom));
  }

  /* 2. hosted page must read backend.json and use the address inside it */
  {
    const hosted = 'https://live.example.trycloudflare.com/webhook/abc/chat';
    const dom = makeDom({ attrs: { 'data-local-webhook': LOCAL } });
    dom.location = { protocol: 'https:', href: 'https://uhygyuf.github.io/rag-support-bot/' };
    const calls = [];
    const sandbox = runWidget(dom, (url) => {
      calls.push(url);
      if (url === 'backend.json') return Promise.resolve({ ok: true, json: () => Promise.resolve({ webhook: hosted }) });
      return Promise.resolve({ ok: true, text: () => Promise.resolve('{"output":"answered from the live backend"}') });
    });
    await tick();
    ask(dom);
    await tick();
    record('hosted page fetches backend.json first', calls[0] === 'backend.json',
      'calls: ' + JSON.stringify(calls));
    record('hosted page posts to the address from backend.json', calls[1] === hosted,
      'calls: ' + JSON.stringify(calls));
  }

  /* 3. backend.json absent (404) must not crash the widget */
  {
    const dom = makeDom({ attrs: { 'data-local-webhook': LOCAL } });
    dom.location = { protocol: 'https:', href: 'https://uhygyuf.github.io/rag-support-bot/' };
    const calls = [];
    const sandbox = runWidget(dom, (url) => {
      calls.push(url);
      if (url === 'backend.json') return Promise.resolve({ ok: false, status: 404 });
      return Promise.resolve({ ok: true, text: () => Promise.resolve('{"output":"x"}') });
    });
    await tick();
    ask(dom);
    await tick();
    record('missing backend.json falls back without throwing', calls.length === 2,
      'calls: ' + JSON.stringify(calls));
  }

  /* 4. backend unreachable must show the offline line, never an HTTP code */
  {
    const dom = makeDom({ attrs: { 'data-local-webhook': LOCAL } });
    dom.location = { protocol: 'file:', href: 'file:///site/index.html' };
    const sandbox = runWidget(dom, () => Promise.reject(new Error('ECONNREFUSED')));
    await tick();
    ask(dom);
    await tick();
    const msg = lastBotMessage(dom);
    record('unreachable backend shows the offline sentence',
      msg.indexOf('our assistant is offline') !== -1, msg);
    record('no HTTP status or exception text reaches the visitor',
      msg.indexOf('500') === -1 && msg.indexOf('ECONNREFUSED') === -1 && msg.indexOf('Error') === -1, msg);
    record('the failure is logged to the console instead', dom.warns.length > 0, dom.warns.join(' | ').slice(0, 120));
  }

  /* 5. hostile text must never become markup: an answer is data, not HTML */
  {
    const dom = makeDom({ attrs: { 'data-local-webhook': LOCAL } });
    dom.location = { protocol: 'file:', href: 'file:///site/index.html' };
    const payload = '<img src=x onerror="window.pwned=1"> <script>window.pwned=2</script>';
    const sandbox = runWidget(dom, () => Promise.resolve({
      ok: true, text: () => Promise.resolve(JSON.stringify({ output: payload }))
    }));
    await tick();
    ask(dom);
    await tick();
    const panel = elementById(dom, 'rgw-panel');
    const log = panel.querySelector('#rgw-log');
    const shown = lastBotMessage(dom);
    record('an answer that contains HTML is shown as text', shown === payload,
      JSON.stringify(shown.slice(0, 32)));
    record('the answer never reaches innerHTML (nothing is parsed or executed)',
      String(log.innerHTML).indexOf('<img') === -1 && sandbox.pwned === undefined,
      'log.innerHTML=' + JSON.stringify(String(log.innerHTML).slice(0, 40)));
  }

  const failed = results.filter((r) => r.status === 'FAIL');
  fs.writeFileSync(path.join(ROOT, 'tests', 'widget_dom-results.json'),
    JSON.stringify(results, null, 2) + '\n');
  console.log('-'.repeat(74));
  console.log('WIDGET DOM: %d cases, %d failed', results.length, failed.length);
  process.exit(failed.length ? 1 : 0);
}

main();
