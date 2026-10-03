/*
 * Terra Nova service worker — served from disk by django-pwa
 * (settings.PWA_SERVICE_WORKER_PATH). Bump VERSION to invalidate caches.
 *
 * Strategy:
 *   navigations      → network-first (3.5s timeout), cached copy, then /offline/
 *   static/fonts     → stale-while-revalidate in a runtime cache
 *   images           → cache-first (they never change client-side)
 *   weather API      → network-first with a cached snapshot for offline
 *   everything else (POST, admin assets) → left to the browser
 */
'use strict';

var VERSION = 'v3';
var PRECACHE = 'terra-precache-' + VERSION;
var RUNTIME = 'terra-runtime-' + VERSION;
var OFFLINE_URL = '/offline/';
var NAV_TIMEOUT = 3500;

var PRECACHE_URLS = [
  OFFLINE_URL,
  '/',
  '/manifest.json',
  '/weather/',
  '/map/',
  '/static/css/terra.css',
  '/static/css/weather.css',
  '/static/css/accessibility.css',
  '/static/css/map.css',
  '/static/css/toastr.css',
  '/static/vendor/toastr/toastr.min.css',
  '/static/js/terra.js',
  '/static/js/toasts.js',
  '/static/js/weather.js',
  '/static/js/accessibility.js',
  '/static/js/net.js',
  '/static/js/map.js',
  '/static/vendor/jquery/jquery.min.js',
  '/static/vendor/toastr/toastr.min.js',
  '/static/img/pwa/icon-192x192.png',
  '/static/img/pwa/icon-512x512.png'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(PRECACHE)
      .then(function (cache) { return cache.addAll(PRECACHE_URLS); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (names) {
        return Promise.all(names
          .filter(function (name) {
            return name.indexOf('terra-') === 0 &&
              name !== PRECACHE && name !== RUNTIME;
          })
          .map(function (name) { return caches.delete(name); }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

/* ---- notifications ---- */

self.addEventListener('notificationclick', function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(function (windows) {
        for (var i = 0; i < windows.length; i++) {
          if ('focus' in windows[i]) return windows[i].focus();
        }
        if (clients.openWindow) {
          return clients.openWindow('/weather/');
        }
        return undefined;
      })
  );
});

self.addEventListener('push', function (event) {
  var data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    data = { body: event.data ? event.data.text() : '' };
  }
  var title = data.headline || data.title || 'Terra Nova — heat alert';
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.message || data.body ||
        'Surface temperatures are rising on Terra Nova.',
      icon: '/static/img/pwa/icon-192x192.png',
      badge: '/static/img/pwa/icon-192x192.png',
      tag: data.tag || 'terra-push',
      data: { url: data.url || '/weather/' },
    })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;

  var url = new URL(request.url);

  if (request.mode === 'navigate') {
    event.respondWith(networkFirstNavigation(request));
    return;
  }

  var isSameOrigin = url.origin === self.location.origin;

  /* Live data: try the network (fast timeout), keep a snapshot, fall
     back to the snapshot so the weather page works offline. */
  if (isSameOrigin && url.pathname.indexOf('/weather/api/') === 0) {
    event.respondWith(networkFirstApi(request, 4000));
    return;
  }

  /* Images never change on the client — serve from cache first. */
  if (isSameOrigin && /\.(?:png|jpe?g|svg|webp|ico)$/.test(url.pathname)) {
    event.respondWith(cacheFirst(request));
    return;
  }

  var isStatic = isSameOrigin && (
    url.pathname.indexOf('/static/') === 0 ||
    url.pathname === '/manifest.json' ||
    /\.(?:woff2?|ttf)$/.test(url.pathname)
  );
  var isFontCdn = url.hostname === 'fonts.googleapis.com' ||
    url.hostname === 'fonts.gstatic.com';

  if (isStatic || isFontCdn) {
    event.respondWith(staleWhileRevalidate(request));
  }
  // Anything else: no respondWith → the browser's default behaviour.
});

function fetchWithTimeout(request, ms) {
  return new Promise(function (resolve, reject) {
    var timer = setTimeout(function () { reject(new Error('sw-timeout')); }, ms);
    fetch(request).then(function (response) {
      clearTimeout(timer);
      resolve(response);
    }, function (err) {
      clearTimeout(timer);
      reject(err);
    });
  });
}

function networkFirstNavigation(request) {
  return caches.open(PRECACHE).then(function (cache) {
    return fetchWithTimeout(request, NAV_TIMEOUT)
      .then(function (response) {
        var url = new URL(request.url);
        var cacheable = response && response.status === 200 &&
          response.type === 'basic' &&
          url.pathname.indexOf('/admin/') !== 0;
        if (cacheable) {
          cache.put(request, response.clone());
        }
        return response;
      })
      .catch(function () {
        return caches.match(request, { ignoreSearch: true })
          .then(function (cached) {
            if (cached) return cached;
            return caches.match(OFFLINE_URL).then(function (offline) {
              return offline || Response.error();
            });
          });
      });
  });
}

function staleWhileRevalidate(request) {
  return caches.open(RUNTIME).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var network = fetch(request)
        .then(function (response) {
          if (response && (response.status === 200 || response.type === 'opaque')) {
            cache.put(request, response.clone()).catch(function () {});
          }
          return response;
        })
        .catch(function () { return null; });

      if (cached) return cached; // serve fast, refresh in the background
      return network.then(function (response) {
        return response || Response.error();
      });
    });
  });
}

/* Live weather: fresh if the network answers, else the last snapshot —
   so /weather/ keeps working with no connectivity at all. */
function networkFirstApi(request, ms) {
  return caches.open(RUNTIME).then(function (cache) {
    return fetchWithTimeout(request, ms)
      .then(function (response) {
        if (response && response.status === 200) {
          cache.put(request, response.clone()).catch(function () {});
        }
        return response;
      })
      .catch(function () {
        return cache.match(request).then(function (cached) {
          return cached || Response.error();
        });
      });
  });
}

/* Static images: cache-first — fastest on slow links, zero revalidation. */
function cacheFirst(request) {
  return caches.open(RUNTIME).then(function (cache) {
    return cache.match(request).then(function (cached) {
      if (cached) return cached;
      return fetch(request).then(function (response) {
        if (response && (response.status === 200 || response.type === 'opaque')) {
          cache.put(request, response.clone()).catch(function () {});
        }
        return response || Response.error();
      });
    });
  });
}
