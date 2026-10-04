/* TERRA NOVA — PWA install prompt
   Captures `beforeinstallprompt`, shows the install button, and hands the
   click back to the browser's native prompt. On iOS (no prompt API) it offers
   "Share → Add to Home Screen" guidance via the toast system. */
(function () {
  'use strict';

  var btn = document.getElementById('install-app');
  if (!btn) { return; }

  var deferred = null;
  var installedLabel = btn.getAttribute('data-label-installed') || 'App installed.';
  var iosLabel = btn.getAttribute('data-label-ios') || '';

  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  var standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;

  function toast(type, message) {
    if (window.terraToast) { window.terraToast[type](message); }
    else if (window.toastr) { window.toastr[type](message); }
  }

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferred = event;
    if (!standalone) { btn.hidden = false; }
  });

  window.addEventListener('appinstalled', function () {
    deferred = null;
    btn.hidden = true;
    toast('success', installedLabel);
  });

  btn.addEventListener('click', function () {
    if (deferred) {
      deferred.prompt();
      deferred.userChoice.then(function (choice) {
        deferred = null;
        if (choice.outcome === 'accepted') {
          btn.hidden = true;
          toast('success', installedLabel);
        }
      });
    } else if (isIOS) {
      toast('info', iosLabel);
    } else {
      btn.hidden = true;
    }
  });

  if (isIOS && !standalone) { btn.hidden = false; }
})();
