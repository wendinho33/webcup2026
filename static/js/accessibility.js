/* TERRA NOVA — accessibility settings, text-to-speech & dictation */
(function () {
  'use strict';

  /* ---------------- preferences ---------------- */
  var KEY = 'terra-a11y';
  var DEFAULTS = {
    textSize: '',
    contrast: false,
    reading: false,
    links: false,
    motion: false,
    rate: 1
  };
  var state = load();

  function load() {
    var merged = {};
    var k;
    for (k in DEFAULTS) merged[k] = DEFAULTS[k];
    try {
      var saved = JSON.parse(localStorage.getItem(KEY) || '{}');
      for (k in DEFAULTS) {
        if (Object.prototype.hasOwnProperty.call(saved, k)) merged[k] = saved[k];
      }
    } catch (err) { /* fall back to defaults */ }
    return merged;
  }

  function persist() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (err) {}
  }

  function setAttr(el, name, value) {
    if (value === null || value === '' || value === false) el.removeAttribute(name);
    else el.setAttribute(name, String(value));
  }

  function apply() {
    var d = document.documentElement;
    setAttr(d, 'data-text-size', state.textSize);
    setAttr(d, 'data-contrast', state.contrast ? 'high' : null);
    setAttr(d, 'data-reading', state.reading ? 'on' : null);
    setAttr(d, 'data-links', state.links ? 'underlined' : null);
    setAttr(d, 'data-motion', state.motion ? 'reduce' : null);
    setAttr(d, 'data-speech-rate', state.rate !== 1 ? state.rate : null);
    document.dispatchEvent(new CustomEvent('terra:a11y-change', { detail: state }));
  }

  function update() { apply(); persist(); }

  /* ---------------- panel ---------------- */
  var panel = document.getElementById('a11y-panel');
  var backdrop = document.querySelector('.a11y-backdrop');
  var opener = document.querySelector('[data-a11y-open]');
  var lastFocus = null;

  if (panel && opener) {
    var focusables = function () {
      return Array.prototype.filter.call(
        panel.querySelectorAll('button, input, select, textarea, a[href]'),
        function (el) { return !el.disabled && el.offsetParent !== null; }
      );
    };

    var onKeydown = function (e) {
      if (e.key === 'Escape') { closePanel(); return; }
      if (e.key !== 'Tab') return;
      var items = focusables();
      if (!items.length) return;
      var first = items[0];
      var last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    };

    var openPanel = function () {
      lastFocus = document.activeElement;
      panel.hidden = false;
      if (backdrop) backdrop.hidden = false;
      requestAnimationFrame(function () {
        panel.classList.add('is-open');
        if (backdrop) backdrop.classList.add('is-open');
      });
      opener.setAttribute('aria-expanded', 'true');
      var closeBtn = panel.querySelector('[data-a11y-close]');
      if (closeBtn) closeBtn.focus();
      document.addEventListener('keydown', onKeydown);
    };

    var closePanel = function () {
      panel.classList.remove('is-open');
      if (backdrop) backdrop.classList.remove('is-open');
      opener.setAttribute('aria-expanded', 'false');
      document.removeEventListener('keydown', onKeydown);
      window.setTimeout(function () {
        panel.hidden = true;
        if (backdrop) backdrop.hidden = true;
      }, 420);
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    };

    opener.addEventListener('click', openPanel);
    Array.prototype.forEach.call(
      panel.querySelectorAll('[data-a11y-close]'),
      function (el) { el.addEventListener('click', closePanel); }
    );
    if (backdrop) backdrop.addEventListener('click', closePanel);
  }

  /* ---------------- sync UI <-> state ---------------- */
  function syncUI() {
    if (!panel) return;
    Array.prototype.forEach.call(
      panel.querySelectorAll('input[data-a11y-key]'),
      function (input) {
        input.checked =
          state[input.getAttribute('data-a11y-key')] === input.value;
      }
    );
    Array.prototype.forEach.call(
      panel.querySelectorAll('input[data-a11y-toggle]'),
      function (input) {
        input.checked = !!state[input.getAttribute('data-a11y-toggle')];
      }
    );
    var rate = panel.querySelector('[data-tts-rate]');
    if (rate) rate.value = state.rate;
    updateRateOut();
  }

  function updateRateOut() {
    var out = panel && panel.querySelector('[data-tts-rate-out]');
    if (out) out.textContent = Number(state.rate).toFixed(1) + '×';
  }

  function a11yStatus(message) {
    var el = panel && panel.querySelector('[data-a11y-status]');
    if (el) el.textContent = message;
  }

  if (panel) {
    panel.addEventListener('change', function (e) {
      var t = e.target;
      if (t.matches('input[data-a11y-key]')) {
        state[t.getAttribute('data-a11y-key')] = t.value;
        update();
      } else if (t.matches('input[data-a11y-toggle]')) {
        state[t.getAttribute('data-a11y-toggle')] = t.checked;
        update();
      } else if (t.matches('[data-tts-rate]')) {
        state.rate = parseFloat(t.value) || 1;
        update();
      }
      syncUI();
    });

    var resetBtn = panel.querySelector('[data-a11y-reset]');
    if (resetBtn) {
      resetBtn.addEventListener('click', function () {
        for (var k in DEFAULTS) state[k] = DEFAULTS[k];
        update();
        syncUI();
        a11yStatus('Settings reset to defaults.');
      });
    }
  }

  window.addEventListener('storage', function (e) {
    if (e.key !== KEY) return;
    state = load();
    apply();
    syncUI();
  });

  apply();
  syncUI();
  /* ---------------- text to speech ---------------- */
  var synth = window.speechSynthesis;
  var supportsTTS = !!synth && typeof window.SpeechSynthesisUtterance !== 'undefined';
  var ttsPlay = panel && panel.querySelector('[data-tts="play"]');
  var ttsPause = panel && panel.querySelector('[data-tts="pause"]');
  var ttsStop = panel && panel.querySelector('[data-tts="stop"]');
  var ttsStatus = panel && panel.querySelector('[data-tts-status]');
  var fab = document.querySelector('[data-a11y-open]');
  var session = 0;
  var playing = false;
  var paused = false;
  var chunks = [];
  var next = 0;

  function setStatus(message) {
    if (ttsStatus) ttsStatus.textContent = message;
  }

  function setPlaying(on) {
    playing = on;
    paused = false;
    if (ttsPlay) ttsPlay.hidden = on;
    if (ttsPause) { ttsPause.hidden = !on; ttsPause.textContent = 'Pause'; }
    if (ttsStop) ttsStop.hidden = !on;
    if (fab) fab.classList.toggle('is-speaking', on);
  }

  function collectText() {
    var root = document.querySelector('main') || document.body;
    var clone = root.cloneNode(true);
    Array.prototype.forEach.call(
      clone.querySelectorAll('script, style, noscript, svg, template'),
      function (node) { node.parentNode.removeChild(node); }
    );
    return (clone.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function chunkText(text, max) {
    var parts = text.match(/[^.!?…]+[.!?…]+["')\]]*|[^.!?…]+/g) || [text];
    var out = [];
    var buf = '';
    for (var i = 0; i < parts.length; i++) {
      if (buf && (buf + parts[i]).length > max) {
        out.push(buf);
        buf = '';
      }
      buf += parts[i];
    }
    if (buf) out.push(buf);
    return out;
  }

  function speakNext(mine) {
    if (mine !== session) return;
    if (next >= chunks.length) {
      setPlaying(false);
      setStatus('Finished reading the page.');
      return;
    }
    var utterance = new SpeechSynthesisUtterance(chunks[next++]);
    utterance.rate = parseFloat(state.rate) || 1;
    utterance.lang = document.documentElement.lang || 'en-US';
    utterance.onend = function () { speakNext(mine); };
    utterance.onerror = function () {
      if (mine === session && !playing) setStatus('Reading stopped.');
    };
    synth.speak(utterance);
  }

  function speak() {
    if (!supportsTTS) return;
    var text = collectText();
    if (!text) { setStatus('There is no text to read on this page.'); return; }
    session += 1;
    var mine = session;
    synth.cancel();
    chunks = chunkText(text, 240);
    next = 0;
    setPlaying(true);
    setStatus('Reading ' + chunks.length + ' segments aloud…');
    speakNext(mine);
  }

  function stopSpeaking(finished) {
    session += 1;
    if (supportsTTS) synth.cancel();
    setPlaying(false);
    setStatus(finished ? 'Finished reading the page.' : 'Reading stopped.');
  }

  if (panel) {
    if (!supportsTTS) {
      [ttsPlay, ttsPause, ttsStop].forEach(function (btn) {
        if (btn) btn.disabled = true;
      });
      setStatus('Speech synthesis is not available in this browser.');
    }
    if (ttsPlay) {
      ttsPlay.addEventListener('click', function () {
        if (playing) stopSpeaking(false); else speak();
      });
    }
    if (ttsPause) {
      ttsPause.addEventListener('click', function () {
        if (!supportsTTS || !playing) return;
        if (!paused) {
          synth.pause(); paused = true;
          ttsPause.textContent = 'Resume';
          setStatus('Paused.');
        } else {
          synth.resume(); paused = false;
          ttsPause.textContent = 'Pause';
          setStatus('Reading…');
        }
      });
    }
    if (ttsStop) {
      ttsStop.addEventListener('click', function () { stopSpeaking(false); });
    }
  }

  window.addEventListener('pagehide', function () {
    session += 1;
    if (supportsTTS) synth.cancel();
  });
  /* ---------------- dictation: speech → text inputs ---------------- */
  var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRec) {
    var recognition = new SpeechRec();
    var currentInput = null;
    var activeMic = null;

    recognition.lang = document.documentElement.lang || 'en';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onresult = function (event) {
      var text = Array.prototype.map.call(event.results, function (result) {
        return result[0].transcript;
      }).join(' ').trim();
      if (currentInput && text) {
        var existing = currentInput.value.trim();
        currentInput.value = existing ? existing + ' ' + text : text;
        currentInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
    };
    recognition.onend = resetMics;
    recognition.onerror = resetMics;

    function resetMics() {
      if (activeMic) activeMic.setAttribute('aria-pressed', 'false');
      activeMic = null;
      currentInput = null;
    }

    Array.prototype.forEach.call(
      document.querySelectorAll('.field input, .mc__log-row input'),
      function (input) {
        var type = (input.type || 'text').toLowerCase();
        var blocked = ['password', 'hidden', 'checkbox', 'radio',
          'submit', 'button', 'file', 'range', 'number'];
        if (blocked.indexOf(type) !== -1) return;
        if (input.closest('.a11y-input')) return;

        var wrap = document.createElement('div');
        wrap.className = 'a11y-input';
        input.parentNode.insertBefore(wrap, input);
        wrap.appendChild(input);

        var mic = document.createElement('button');
        mic.type = 'button';
        mic.className = 'a11y-mic';
        mic.setAttribute('aria-pressed', 'false');
        var label = input.id
          ? document.querySelector('label[for="' + input.id + '"]')
          : null;
        mic.setAttribute('aria-label',
          'Dictate with your voice' + (label ? ' — ' + label.textContent.trim() : ''));
        mic.title = 'Dictate (speech to text)';
        mic.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" ' +
          'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">' +
          '<rect x="9" y="3" width="6" height="11" rx="3"/>' +
          '<path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/></svg>';
        mic.addEventListener('click', function () {
          if (activeMic === mic) { recognition.stop(); return; }
          resetMics();
          try {
            currentInput = input;
            activeMic = mic;
            mic.setAttribute('aria-pressed', 'true');
            recognition.start();
          } catch (err) {
            resetMics();
          }
        });
        wrap.appendChild(mic);
      }
    );
  }
})();
