/* TERRA NOVA — transport: live countdowns, board selection, fare maths */
(function () {
  'use strict';

  var pad = function (n) { return n < 10 ? '0' + n : String(n); };

  /* ---- departure countdowns (data-countdown = epoch seconds) ---- */
  var cells = Array.prototype.slice.call(
    document.querySelectorAll('[data-countdown]'),
  );
  function tickCountdowns() {
    var now = Math.floor(Date.now() / 1000);
    cells.forEach(function (el) {
      var until = parseInt(el.getAttribute('data-countdown'), 10) || 0;
      var diff = until - now;
      if (diff <= 0) {
        el.textContent = 'Departed';
        el.classList.add('is-gone');
        el.classList.remove('is-soon');
        return;
      }
      var h = Math.floor(diff / 3600);
      var m = Math.floor((diff % 3600) / 60);
      var s = diff % 60;
      el.textContent = (h > 0 ? pad(h) + ':' : '') + pad(m) + ':' + pad(s);
      el.classList.toggle('is-soon', diff < 300);
      el.classList.remove('is-gone');
    });
  }
  if (cells.length) {
    tickCountdowns();
    window.setInterval(tickCountdowns, 1000);
  }

  /* ---- board "Select" → purchase console ---- */
  var departSelect = document.querySelector('[data-depart-select]');
  document.querySelectorAll('[data-select]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!departSelect) return;
      departSelect.value = btn.getAttribute('data-value');
      departSelect.dispatchEvent(new Event('change', { bubbles: true }));
      var buy = document.getElementById('buy');
      if (buy) buy.scrollIntoView({ behavior: 'smooth', block: 'start' });
      departSelect.focus({ preventScroll: true });
    });
  });

  /* ---- live fare calculation (balance − fare = result) ---- */
  var calc = document.querySelector('[data-calc]');
  if (calc) {
    var balance = parseFloat(calc.getAttribute('data-balance')) || 0;
    var balanceOut = calc.querySelector('[data-calc-balance]');
    var fareOut = calc.querySelector('[data-calc-fare]');
    var resultOut = calc.querySelector('[data-calc-result]');

    var currentFare = function () {
      var base = 0;
      if (departSelect && departSelect.selectedOptions.length) {
        base = parseFloat(
          departSelect.selectedOptions[0].getAttribute('data-fare'),
        ) || 0;
      }
      var checked = document.querySelector('input[name="traveler_id"]:checked');
      var factor = checked
        ? (parseFloat(checked.getAttribute('data-factor')) || 1)
        : 1;
      return base * factor;
    };
    var fmt = function (value) {
      return value.toLocaleString('en-US', {
        minimumFractionDigits: 6,
        maximumFractionDigits: 6,
      });
    };
    var refresh = function () {
      var fare = currentFare();
      if (fareOut) fareOut.textContent = fmt(fare);
      if (resultOut) resultOut.textContent = fmt(Math.max(0, balance - fare));
      if (balanceOut) balanceOut.textContent = fmt(balance);
    };

    if (departSelect) departSelect.addEventListener('change', refresh);
    document.querySelectorAll('input[name="traveler_id"]').forEach(function (r) {
      r.addEventListener('change', refresh);
    });
    refresh();
  }
})();
