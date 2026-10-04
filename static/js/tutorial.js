/* TERRA NOVA — first-login tour */
(function () {
  'use strict';

  var tut = document.querySelector('[data-tutorial]');
  if (!tut) { return; }

  var form = tut.querySelector('[data-tut-form]');
  var dismiss = function () {
    if (form && typeof form.submit === 'function') { form.submit(); }
  };

  var closeBtn = tut.querySelector('[data-tut-close]');
  if (closeBtn) { closeBtn.addEventListener('click', dismiss); }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { dismiss(); }
  });

  var steps = Array.prototype.slice.call(tut.querySelectorAll('[data-tut-step]'));
  if (steps.length < 2) { return; }

  var next = tut.querySelector('[data-tut-next]');
  var prev = tut.querySelector('[data-tut-prev]');
  var counter = tut.querySelector('[data-tut-counter]');
  var dotsWrap = tut.querySelector('[data-tut-dots]');
  var i = 0;

  if (dotsWrap) {
    steps.forEach(function (_, idx) {
      var dot = document.createElement('button');
      dot.type = 'button';
      dot.className = 'tut__dot';
      dot.setAttribute('data-tut-dot', '');
      dot.addEventListener('click', function () { i = idx; render(); });
      dotsWrap.appendChild(dot);
    });
  }

  var render = function () {
    steps.forEach(function (step, idx) {
      step.classList.toggle('is-active', idx === i);
    });
    if (prev) { prev.hidden = i === 0; }
    if (next) { next.hidden = i === steps.length - 1; }
    if (counter) { counter.textContent = (i + 1) + ' / ' + steps.length; }
    if (dotsWrap) {
      Array.prototype.slice.call(dotsWrap.querySelectorAll('[data-tut-dot]'))
        .forEach(function (dot, idx) {
          dot.classList.toggle('is-active', idx === i);
        });
    }
  };

  if (next) { next.addEventListener('click', function () { i = Math.min(i + 1, steps.length - 1); render(); }); }
  if (prev) { prev.addEventListener('click', function () { i = Math.max(i - 1, 0); render(); }); }

  tut.classList.add('tut--stepped');
  render();
})();
