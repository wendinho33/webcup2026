/* TERRA NOVA — weather page: heat notifications, polling, simulation */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var STORE_NOTIFIED = 'terra-notified-days';

  function loadDays() {
    try {
      var v = JSON.parse(localStorage.getItem(STORE_NOTIFIED));
      return Array.isArray(v) ? v : [];
    } catch (e) { return []; }
  }
  function saveDays(days) {
    try { localStorage.setItem(STORE_NOTIFIED, JSON.stringify(days)); } catch (e) {}
  }
  function todayIso() {
    var d = new Date();
    return d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function fallbackNotify(title, opts) {
    try {
      var n = new Notification(title, opts);
      n.onclick = function () {
        window.focus();
        if (opts.data && opts.data.url) window.location.href = opts.data.url;
        n.close();
      };
      return true;
    } catch (e) { return false; }
  }

  function notify(title, body, tag) {
    if (!('Notification' in window) || Notification.permission !== 'granted') {
      return false;
    }
    var opts = {
      body: body,
      tag: tag,
      icon: '/static/img/pwa/icon-192x192.png',
      badge: '/static/img/pwa/icon-192x192.png',
      data: { url: '/weather/' },
    };
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      navigator.serviceWorker.ready.then(function (reg) {
        reg.showNotification(title, opts).catch(function () {
          fallbackNotify(title, opts);
        });
      }).catch(function () { fallbackNotify(title, opts); });
      return true;
    }
    return fallbackNotify(title, opts);
  }

  /* ---------- weather page ---------- */
  var wx = document.querySelector('[data-wx]');
  if (wx) {

  var stateEl = document.querySelector('[data-notify-state]');
  var enableBtn = document.querySelector('[data-notify-enable]');
  var testBtn = document.querySelector('[data-notify-test]');
  var statusUrl = wx.getAttribute('data-status-url');
  var triggerUrl = wx.getAttribute('data-trigger-url');
  var firstLoad = true;

  function setState(text, blocked) {
    if (!stateEl) return;
    stateEl.textContent = text;
    stateEl.classList.toggle('is-blocked', !!blocked);
  }

  function permissionState() {
    if (!('Notification' in window)) {
      setState('STATUS: UNSUPPORTED — THIS BROWSER CANNOT SHOW NOTIFICATIONS', true);
      if (enableBtn) enableBtn.disabled = true;
      return;
    }
    if (Notification.permission === 'granted') {
      setState('STATUS: GRANTED — HEAT ALERTS WILL REACH THIS DEVICE');
      if (enableBtn) enableBtn.textContent = 'Push alerts enabled ✓';
    } else if (Notification.permission === 'denied') {
      setState('STATUS: BLOCKED — ALLOW NOTIFICATIONS IN YOUR BROWSER SETTINGS', true);
      if (enableBtn) enableBtn.disabled = true;
    } else {
      setState('STATUS: NOT ENABLED — PRESS THE BUTTON BELOW');
    }
  }

  function handleAlerts(alerts) {
    var today = todayIso();
    var days = loadDays();
    var changed = false;
    alerts.forEach(function (a) {
      // One trigger per simulation day: today (and any past-unseen day),
      // never the whole future window at once.
      if (a.day <= today && days.indexOf(a.day) === -1) {
        notify(a.headline, a.message, 'terra-alert-' + a.id);
        days.push(a.day);
        changed = true;
      }
    });
    if (changed) saveDays(days);
  }

  function poll(initial) {
    if (!statusUrl) return;
    fetch(statusUrl + (initial ? '' : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data) return;
        if (!initial || firstLoad) handleAlerts(data.alerts || []);
        firstLoad = false;
      })
      .catch(function () {});
  }

  if (enableBtn) {
    enableBtn.addEventListener('click', function () {
      if (!('Notification' in window)) { permissionState(); return; }
      Notification.requestPermission().then(function () {
        permissionState();
        if (Notification.permission === 'granted') {
          notify('Heat alerts enabled',
            'Terra Nova will warn you when surface temperatures rise. ' +
            'The simulation issues one alert per day for the next week.',
            'terra-ack');
          poll(false);
        }
      });
    });
  }

  if (testBtn) {
    testBtn.addEventListener('click', function () {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(function () {
          permissionState();
          if (Notification.permission === 'granted') fire();
        });
      } else {
        fire();
      }

      function fire() {
        testBtn.disabled = true;
        setState('STATUS: FIRING SIMULATION…');
        fetch(triggerUrl, {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'X-CSRFToken': csrfToken(),
            'X-Requested-With': 'XMLHttpRequest',
          },
        })
          .then(function (r) { return r.json(); })
          .then(function (alert) {
            notify(alert.headline, alert.message, 'terra-sim-' + alert.id);
            setState('STATUS: SIMULATION FIRED — ' +
              alert.headline.toUpperCase() + ' · ' + alert.temp + '°C');
          })
          .catch(function () { setState('STATUS: TRIGGER FAILED — RETRY', true); })
          .then(function () { testBtn.disabled = false; });
      }
    });
  }

  permissionState();
  poll(true);   /* one initial check is essential even on 512 kbps */
  /* Background polling is a luxury: skip it entirely on lite links. */
  var pollTimer = 0;
  function startPolling() {
    if (pollTimer) return;
    if (document.documentElement.getAttribute('data-net-tier') === 'lite') return;
    pollTimer = window.setInterval(function () { poll(false); }, 30000);
  }
  startPolling();
  document.addEventListener('terra:net', startPolling);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden &&
        document.documentElement.getAttribute('data-net-tier') !== 'lite') {
      poll(false);
    }
  });
  }
})();
