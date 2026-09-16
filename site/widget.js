/* Minimal chat widget for the RAG support bot.
   Usage: <script src="widget.js" data-webhook="http://127.0.0.1:5678/webhook/<id>/chat" data-title="Support"></script>
   Posts the n8n Chat Trigger protocol {action:'sendMessage', sessionId, chatInput}
   and renders the reply field {output}. */
(function () {
  var me = document.currentScript;
  var WEBHOOK = (me && me.getAttribute('data-webhook')) || 'http://127.0.0.1:5678/webhook/chat';
  var TITLE = (me && me.getAttribute('data-title')) || 'Support';
  var sessionId = 's-' + Math.random().toString(36).slice(2, 10);

  var css = document.createElement('style');
  css.textContent = [
    '#rgw-btn{position:fixed;right:22px;bottom:22px;z-index:99999;border:0;border-radius:50%;width:56px;height:56px;',
    'background:#1d1a17;color:#fff;font-size:24px;cursor:pointer;box-shadow:0 8px 26px rgba(0,0,0,.25)}',
    '#rgw-panel{position:fixed;right:22px;bottom:92px;z-index:99999;width:340px;max-height:520px;display:none;',
    'flex-direction:column;background:#fff;border:1px solid #e6ded3;border-radius:16px;overflow:hidden;',
    'box-shadow:0 18px 50px rgba(0,0,0,.22);font:15px/1.5 "Segoe UI",system-ui,sans-serif;color:#1d1a17}',
    '#rgw-panel.open{display:flex}',
    '#rgw-head{padding:13px 16px;background:#1d1a17;color:#fff;font-weight:700;font-size:14px}',
    '#rgw-log{flex:1;overflow:auto;padding:14px;background:#faf7f2}',
    '.rgw-msg{margin-bottom:10px;padding:9px 12px;border-radius:12px;max-width:85%;white-space:pre-wrap}',
    '.rgw-me{background:#1d1a17;color:#fff;margin-left:auto}',
    '.rgw-bot{background:#fff;border:1px solid #e6ded3}',
    '.rgw-form{display:flex;border-top:1px solid #e6ded3}',
    '#rgw-in{flex:1;border:0;padding:13px;font:inherit;outline:none}',
    '#rgw-send{border:0;background:#b4552d;color:#fff;padding:0 18px;font:inherit;font-weight:600;cursor:pointer}',
    '.rgw-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}'
  ].join('');
  document.head.appendChild(css);

  var btn = document.createElement('button');
  btn.id = 'rgw-btn'; btn.type = 'button'; btn.textContent = '💬';
  btn.title = TITLE; btn.setAttribute('aria-label', 'Open ' + TITLE + ' chat');
  var panel = document.createElement('div');
  panel.id = 'rgw-panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', TITLE + ' chat window');
  panel.innerHTML = '<div id="rgw-head"></div><div id="rgw-log" aria-live="polite"></div>'
    + '<form class="rgw-form"><label for="rgw-in" class="rgw-sr">Your question</label>'
    + '<input id="rgw-in" placeholder="Ask about shipping, grind, returns…" autocomplete="off">'
    + '<button id="rgw-send" type="submit">Send</button></form>';
  panel.querySelector('#rgw-head').textContent = TITLE;
  document.body.appendChild(btn); document.body.appendChild(panel);

  var log = panel.querySelector('#rgw-log'), input = panel.querySelector('#rgw-in');
  btn.addEventListener('click', function () {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) input.focus();
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && panel.classList.contains('open')) {
      panel.classList.remove('open'); btn.focus();
    }
  });

  function add(text, who) {
    var d = document.createElement('div');
    d.className = 'rgw-msg ' + (who === 'me' ? 'rgw-me' : 'rgw-bot');
    d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  }

  panel.querySelector('form').addEventListener('submit', function (e) {
    e.preventDefault();
    var q = input.value.trim(); if (!q) return;
    input.value = ''; add(q, 'me');
    var pending = add('…', 'bot');
    fetch(WEBHOOK, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'sendMessage', sessionId: sessionId, chatInput: q })
    }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    }).then(function (t) {
      var out = t;
      try { var j = JSON.parse(t); out = j.output || j.text || j.reply || t; } catch (_) {}
      pending.textContent = out;
    }).catch(function (err) { pending.textContent = 'Connection error: ' + err.message; });
  });

  add('Hi! Ask me anything about our coffee, shipping, subscriptions or wholesale.', 'bot');
})();
