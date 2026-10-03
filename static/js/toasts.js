/* ---------------------------------------------------------------
 * Terra Nova — toastr message system
 *
 * 1. Renders the Django messages queued by the server (the
 *    server-rendered `[data-toasts]` block in base.html) through
 *    toastr, then removes that block so nothing is shown twice.
 * 2. Listens to every form submission on the page and shows
 *    immediate "sending" feedback, plus a validation warning when
 *    the browser reports the form as invalid.
 * 3. Exposes window.terraToast so the other scripts on the page can
 *    raise a message themselves (success / error / warning / info).
 *
 * Progressive enhancement: if jQuery or toastr failed to load, this
 * file does nothing and the server-rendered toasts stay visible, so
 * messages always reach the user.
 * --------------------------------------------------------------- */
(function () {
  'use strict';

  var $ = window.jQuery;
  var toastr = window.toastr;
  if (!$ || !toastr) { return; }

  /* ---------------- configuration ---------------- */

  var TITLES = {
    success: 'Confirmed',
    error: 'Transmission failed',
    warning: 'Heads up',
    info: 'Mission Control',
    debug: 'Mission Control'
  };

  toastr.options = {
    closeButton: true,
    progressBar: true,
    preventDuplicates: true,
    newestOnTop: true,
    tapToDismiss: true,
    positionClass: 'toast-bottom-right',
    showDuration: 250,
    hideDuration: 300,
    timeOut: 5000,
    extendedTimeOut: 2000,
    escapeHtml: true
  };

  /* Map a tag to a toastr type — unknown tags fall back to info. */
  function normalise(type) {
    return (type === 'success' || type === 'error' ||
            type === 'warning' || type === 'info') ? type : 'info';
  }

  /* ---------------- public helper ---------------- */

  var api = {
    show: function (type, message, title, opts) {
      type = normalise(type);
      return toastr[type](String(message), title || TITLES[type], opts || {});
    },
    success: function (message, title, opts) {
      return api.show('success', message, title, opts);
    },
    error: function (message, title, opts) {
      return api.show('error', message, title, opts);
    },
    warning: function (message, title, opts) {
      return api.show('warning', message, title, opts);
    },
    info: function (message, title, opts) {
      return api.show('info', message, title, opts);
    },
    /* Drop every toast currently on screen (used by the "sending"
       toast when an AJAX handler takes over the submission). */
    clear: function () { toastr.clear(); }
  };
  window.terraToast = api;

  /* ---------------- 1. server messages → toastr ---------------- */

  function drainServerMessages() {
    var box = document.querySelector('[data-toasts]');
    if (!box) { return; }

    var items = box.querySelectorAll('.toast');
    for (var i = 0; i < items.length; i++) {
      var el = items[i];
      var text = (el.textContent || '').trim();
      if (!text) { continue; }

      /* `<div class="toast toast--success">…</div>` → success */
      var tag = (el.className.match(/toast--([a-z]+)/) || [])[1] || '';
      var type = tag === 'debug' ? 'info' : normalise(tag);
      toastr[type](text, TITLES[type]);
    }

    if (box.parentNode) { box.parentNode.removeChild(box); }
  }

  /* ---------------- 2. feedback on every form submit ---------------- */

  /* Extra copy a template can tune:
     <form data-toast-sending="Launching…">                     */
  function sendingCopy(form) {
    return {
      title: form.getAttribute('data-toast-title') || 'Transmitting',
      message: form.getAttribute('data-toast-sending') ||
               'Sending your entry…'
    };
  }

  function unlock(form) {
    if (form && form.getAttribute('data-terra-sending') === '1') {
      form.removeAttribute('data-terra-sending');
    }
  }

  function onSubmit(event) {
    var form = event.target;
    if (!form || form.tagName !== 'FORM') { return; }

    /* Opt out: <form data-no-toast> */
    if (form.hasAttribute('data-no-toast')) { return; }

    /* Never let one form fire twice while its request is in flight. */
    if (form.getAttribute('data-terra-sending') === '1') {
      event.preventDefault();
      return;
    }

    /* `novalidate` forms are validated on the server on purpose —
       respect that and let the round trip happen. */
    if (!form.hasAttribute('novalidate') &&
        typeof form.checkValidity === 'function' &&
        !form.checkValidity()) {
      event.preventDefault();
      api.error('Some fields need your attention.', 'Check the form');
      return;
    }

    form.setAttribute('data-terra-sending', '1');
    var copy = sendingCopy(form);
    var handle = toastr.info(copy.message, copy.title, {
      timeOut: 0,
      extendedTimeOut: 0,
      tapToDismiss: false,
      closeButton: false,
      progressBar: false
    });

    /* If another handler cancelled the submit (an AJAX/fetch form),
       the page is not going anywhere — clear the pending toast. */
    window.setTimeout(function () {
      if (event.defaultPrevented) {
        unlock(form);
        toastr.clear(handle);
      }
    }, 0);
  }

  document.addEventListener('submit', onSubmit, true);

  /* Coming back to the page from the bfcache leaves the flags set. */
  window.addEventListener('pageshow', function (event) {
    if (!event.persisted) { return; }
    var forms = document.querySelectorAll('[data-terra-sending]');
    for (var i = 0; i < forms.length; i++) { unlock(forms[i]); }
  });

  /* ---------------- boot ---------------- */

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', drainServerMessages);
  } else {
    drainServerMessages();
  }
})();
