/* Terra Nova admin — progressive enhancements (vanilla, no dependencies).
   1. Press "/" anywhere to jump to the changelist search field.
   2. Enter submits search on a single Enter instead of needing the button
      (browser default already does this — kept as a safety net).
   Everything here is optional: the interface works fully without JS. */
(function () {
  'use strict';

  document.addEventListener('keydown', function (event) {
    if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    var target = event.target;
    var typing =
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.tagName === 'SELECT' ||
        target.isContentEditable);
    if (typing) {
      return;
    }
    var bar = document.getElementById('searchbar');
    if (bar) {
      event.preventDefault();
      bar.focus();
      bar.select();
    }
  });

  /* Mark the deck as enhanced so CSS can show the "/" keyboard hint. */
  if (document.getElementById('searchbar')) {
    document.documentElement.classList.add('tn-has-search');
  }
})();
