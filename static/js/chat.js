/* TERRA NOVA — Terra Chat: live polling + quick prompts */
(function () {
  'use strict';

  /* quick-start chips fill the welcome composer */
  document.querySelectorAll('[data-quick]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var input = document.getElementById('chat-input');
      if (!input) return;
      input.value = btn.getAttribute('data-quick') || '';
      input.focus();
    });
  });

  var stream = document.getElementById('chat-stream');
  if (!stream) return;

  var pollUrl = stream.getAttribute('data-poll-url');
  if (!pollUrl) return;

  var after = 0;
  stream.querySelectorAll('.msg[data-id]').forEach(function (el) {
    var id = parseInt(el.getAttribute('data-id'), 10);
    if (id > after) after = id;
  });

  var chip = document.querySelector('[data-status-chip]');

  function nearBottom() {
    return stream.scrollHeight - stream.scrollTop - stream.clientHeight < 140;
  }

  function addMessage(m) {
    var stick = nearBottom();
    var wrap = document.createElement('div');
    wrap.className = 'msg msg--' + m.role;
    wrap.setAttribute('data-id', String(m.id));

    var meta = document.createElement('div');
    meta.className = 'msg__meta mono';
    var who = document.createElement('span');
    who.className = 'msg__who';
    who.textContent = m.name;
    var time = document.createElement('span');
    time.textContent = m.time;
    meta.appendChild(who);
    meta.appendChild(time);

    var body = document.createElement('div');
    body.className = 'msg__body';
    body.textContent = m.body; // safe: no HTML injection

    wrap.appendChild(meta);
    wrap.appendChild(body);
    stream.appendChild(wrap);
    if (m.id > after) after = m.id;
    if (stick) stream.scrollTop = stream.scrollHeight;
  }

  var busy = false;
  function poll() {
    if (busy || document.hidden) return;
    busy = true;
    fetch(pollUrl + '?after=' + after, { credentials: 'same-origin' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (!data) return;
        (data.messages || []).forEach(addMessage);
        if (chip && data.status_label) {
          chip.textContent = data.status_label;
          chip.className = 'chat__chip chat__chip--' + data.status;
          chip.setAttribute('data-status-chip', '');
        }
      })
      .catch(function () { /* offline — try next tick */ })
      .then(function () { busy = false; });
  }

  stream.scrollTop = stream.scrollHeight;
  window.setInterval(poll, 5000);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) poll();
  });
})();
