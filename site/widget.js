/* Chat widget for the RAG support bot (n8n Chat Trigger).
   Usage:
     <script src="widget.js"
             data-webhook="http://127.0.0.1:5678/webhook/<id>/chat"
             data-title="Harbor Support"
             data-cta="Need coffee help?"
             data-welcome="Hi! ..."
             data-quick-replies="Question one|Question two|..."></script>

   Talks to n8n with the chat protocol {action:'sendMessage', sessionId, chatInput}
   and renders the reply field {output}. */
(function () {
  var me = document.currentScript;

  function attr(name, fallback) {
    var v = me && me.getAttribute(name);
    return (v && v.length) ? v : fallback;
  }

  var WEBHOOK = attr('data-webhook', 'http://127.0.0.1:5678/webhook/chat');
  var TITLE   = attr('data-title', 'Support');
  var CTA     = attr('data-cta', 'Need help?');
  var WELCOME = attr('data-welcome',
    'Hi! I answer only from this company\'s own pages, and I pass anything I cannot answer to a human.');
  var QUICK   = attr('data-quick-replies',
    'How long does US shipping take?|Do you ship to Canada?|How much is the Ethiopia Guji?|' +
    'Can I pause my subscription?|Do you offer wholesale pricing?|I want to talk to a human').split('|');
  var OFFLINE = attr('data-offline',
    'Sorry — our assistant is offline right now. Please email us and a human will reply as soon as we can.');
  var TIMEOUT_MS = parseInt(attr('data-timeout-ms', '45000'), 10) || 45000;

  var sessionId = 's-' + Math.random().toString(36).slice(2, 10);

  /* ---------- styles ---------- */
  var css = document.createElement('style');
  css.textContent = [
    '#rgw-btn{position:fixed;right:22px;bottom:22px;z-index:99999;border:0;border-radius:26px;',
    'padding:13px 20px;background:#1d1a17;color:#fff;font:600 15px/1 "Segoe UI",system-ui,sans-serif;',
    'cursor:pointer;box-shadow:0 8px 26px rgba(0,0,0,.25);display:flex;align-items:center;gap:8px}',
    '#rgw-btn:hover{background:#2c2723}',
    '#rgw-teaser{position:fixed;right:22px;bottom:84px;z-index:99999;max-width:280px;background:#fff;',
    'border:1px solid #e6ded3;border-radius:14px;padding:12px 30px 12px 14px;box-shadow:0 12px 34px rgba(0,0,0,.16);',
    'font:14px/1.5 "Segoe UI",system-ui,sans-serif;color:#1d1a17;display:none}',
    '#rgw-teaser.show{display:block}',
    '#rgw-teaser-x{position:absolute;right:7px;top:5px;border:0;background:transparent;cursor:pointer;',
    'font-size:15px;line-height:1;color:#8a8078}',
    '#rgw-panel{position:fixed;right:22px;bottom:92px;z-index:99999;width:352px;max-height:540px;display:none;',
    'flex-direction:column;background:#fff;border:1px solid #e6ded3;border-radius:16px;overflow:hidden;',
    'box-shadow:0 18px 50px rgba(0,0,0,.22);font:15px/1.5 "Segoe UI",system-ui,sans-serif;color:#1d1a17}',
    '#rgw-panel.open{display:flex}',
    '#rgw-head{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;',
    'background:#1d1a17;color:#fff;font-weight:700;font-size:14px}',
    '#rgw-close{border:0;background:transparent;color:#fff;font-size:18px;line-height:1;cursor:pointer}',
    '#rgw-log{flex:1;overflow:auto;padding:14px;background:#faf7f2}',
    '.rgw-msg{margin-bottom:10px;padding:9px 12px;border-radius:12px;max-width:88%;white-space:pre-wrap}',
    '.rgw-me{background:#1d1a17;color:#fff;margin-left:auto}',
    '.rgw-bot{background:#fff;border:1px solid #e6ded3}',
    '#rgw-quick{display:flex;flex-direction:column;gap:7px;padding:0 14px 12px;background:#faf7f2}',
    '.rgw-chip{text-align:left;border:1px solid #e0d6c8;background:#fff;border-radius:10px;padding:9px 12px;',
    'font:14px/1.35 inherit;color:#1d1a17;cursor:pointer}',
    '.rgw-chip:hover{border-color:#b4552d;color:#b4552d}',
    '.rgw-form{display:flex;border-top:1px solid #e6ded3}',
    '#rgw-in{flex:1;border:0;padding:13px;font:inherit;outline:none}',
    '#rgw-send{border:0;background:#b4552d;color:#fff;padding:0 18px;font:inherit;font-weight:600;cursor:pointer}',
    '.rgw-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}'
  ].join('');
  document.head.appendChild(css);

  /* ---------- markup ---------- */
  var btn = document.createElement('button');
  btn.id = 'rgw-btn'; btn.type = 'button';
  btn.innerHTML = '<span aria-hidden="true">💬</span><span id="rgw-btn-label"></span>';
  btn.setAttribute('aria-label', CTA + ' — open ' + TITLE + ' chat');
  document.body.appendChild(btn);
  btn.querySelector('#rgw-btn-label').textContent = CTA;

  var teaser = document.createElement('div');
  teaser.id = 'rgw-teaser';
  teaser.innerHTML = '<button id="rgw-teaser-x" aria-label="Dismiss message">✕</button>'
    + '<div id="rgw-teaser-t"></div>';
  teaser.querySelector('#rgw-teaser-t').textContent = TITLE + ': ' + WELCOME;
  document.body.appendChild(teaser);

  var panel = document.createElement('div');
  panel.id = 'rgw-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', TITLE + ' chat window');
  panel.innerHTML =
    '<div id="rgw-head"><span id="rgw-head-t"></span>'
    + '<button id="rgw-close" type="button" aria-label="Close chat">✕</button></div>'
    + '<div id="rgw-log" aria-live="polite"></div>'
    + '<div id="rgw-quick"></div>'
    + '<form class="rgw-form">'
    + '<label for="rgw-in" class="rgw-sr">Your question</label>'
    + '<input id="rgw-in" placeholder="Type your question here" autocomplete="off">'
    + '<button id="rgw-send" type="submit">Send</button></form>';
  panel.querySelector('#rgw-head-t').textContent = TITLE;
  document.body.appendChild(panel);

  var log = panel.querySelector('#rgw-log');
  var input = panel.querySelector('#rgw-in');
  var quick = panel.querySelector('#rgw-quick');

  function add(text, who) {
    var d = document.createElement('div');
    d.className = 'rgw-msg ' + (who === 'me' ? 'rgw-me' : 'rgw-bot');
    d.textContent = text;
    log.appendChild(d); log.scrollTop = log.scrollHeight;
    return d;
  }

  function renderChips() {
    quick.textContent = '';
    QUICK.forEach(function (q) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'rgw-chip'; b.textContent = q;
      b.addEventListener('click', function () { send(q); });
      quick.appendChild(b);
    });
  }

  function openPanel() {
    panel.classList.add('open');
    teaser.classList.remove('show');
    input.focus();
  }
  function closePanel() {
    panel.classList.remove('open');
    btn.focus();
  }

  btn.addEventListener('click', function () {
    if (panel.classList.contains('open')) { closePanel(); } else { openPanel(); }
  });
  panel.querySelector('#rgw-close').addEventListener('click', closePanel);
  teaser.querySelector('#rgw-teaser-x').addEventListener('click', function () {
    teaser.classList.remove('show');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && panel.classList.contains('open')) { closePanel(); }
  });

  /* ---------- send ---------- */
  function send(text) {
    var q = String(text == null ? input.value : text).trim();
    if (!q) { return; }
    input.value = '';
    add(q, 'me');
    quick.textContent = '';                 /* the starting options are used once */
    var pending = add('…', 'bot');

    var ctrl = (typeof AbortController === 'function') ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS) : null;

    fetch(WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'sendMessage', sessionId: sessionId, chatInput: q }),
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) {
      if (!r.ok) { throw new Error('HTTP ' + r.status); }
      return r.text();
    }).then(function (t) {
      if (timer) { clearTimeout(timer); }
      var out = t;
      try { var j = JSON.parse(t); out = j.output || j.text || j.reply || t; } catch (_) {}
      pending.textContent = out;
    }).catch(function (err) {
      if (timer) { clearTimeout(timer); }
      if (window.console && console.warn) { console.warn('[support widget]', err); }
      pending.textContent = OFFLINE;       /* visitors never see a stack trace */
    });
  }

  panel.querySelector('form').addEventListener('submit', function (e) {
    e.preventDefault();
    send(input.value);
  });

  /* ---------- first paint ---------- */
  add(WELCOME, 'bot');
  renderChips();
  if (!window.sessionStorage || !sessionStorage.getItem('rgw-teaser-shown')) {
    setTimeout(function () {
      if (!panel.classList.contains('open')) { teaser.classList.add('show'); }
      try { sessionStorage.setItem('rgw-teaser-shown', '1'); } catch (_) {}
    }, 1800);
  }
})();
