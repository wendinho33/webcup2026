/* Terra Nova — connection tier + offline awareness.
 *
 * Measures the link and publishes a tier on <html data-net-tier>:
 *   full     — comfortable connection, everything renders
 *   balanced — ≤ 1 Mbps: pages stay, background polling stops
 *   lite     — ≤ 512 kbps or Save-Data: essential content only
 * The tier is written to the tn_net cookie so Django can drop
 * non-essential blocks server-side on the next request, and
 * broadcast as a `terra:net` event for live consumers (map, weather).
 */
(function () {
  'use strict';

  var COOKIE = 'tn_net';
  var LITE_KBPS = 512;       // ≤ 512 kbps → essential-only
  var BALANCED_KBPS = 1024;  // ≤ 1 Mbps  → essential-only+

  var root = document.documentElement;

  function classify(downlink, effectiveType, saveData) {
    if (saveData || effectiveType === 'slow-2g' || effectiveType === '2g') return 'lite';
    if (typeof downlink === 'number' && downlink > 0) {
      if (downlink <= 0.5) return 'lite';      // ≤ 512 kbps
      if (downlink <= 1) return 'balanced';    // ≤ 1 Mbps
      return 'full';
    }
    if (effectiveType === '3g') return 'balanced';
    if (effectiveType === '4g') return 'full';
    return null; // unknown → probe
  }

  function apply(tier, source) {
    if (tier !== 'lite' && tier !== 'balanced') tier = 'full';
    root.setAttribute('data-net-tier', tier);
    try {
      document.cookie = COOKIE + '=' + tier +
        '; path=/; max-age=2592000; SameSite=Lax';
    } catch (err) { /* private mode — server falls back to full */ }
    document.dispatchEvent(new CustomEvent('terra:net', {
      detail: { tier: tier, source: source },
    }));
  }

  var conn = navigator.connection ||
    navigator.mozConnection || navigator.webkitConnection;
  var fromApi = classify(conn && conn.downlink,
    conn && conn.effectiveType, conn && conn.saveData);

  if (fromApi) {
    apply(fromApi, 'api');
  } else if (window.fetch && window.performance && navigator.onLine !== false) {
    /* No NetworkInformation API (Safari/Firefox): time a ~20 KB asset.
       Round-trip dominates so it over-estimates — but it still separates
       a 2G link from broadband. */
    var t0 = performance.now();
    fetch('/static/img/pwa/icon-192x192.png', {
      cache: 'no-store', credentials: 'omit',
    })
      .then(function (r) { return r.arrayBuffer(); })
      .then(function (buf) {
        var secs = Math.max((performance.now() - t0) / 1000, 0.02);
        var kbps = (buf.byteLength * 8) / secs / 1000;
        apply(kbps <= LITE_KBPS ? 'lite'
          : kbps <= BALANCED_KBPS ? 'balanced' : 'full', 'probe');
      })
      .catch(function () { apply('full', 'fallback'); });
  } else {
    apply('full', 'fallback');
  }

  if (conn && conn.addEventListener) {
    conn.addEventListener('change', function () {
      var t = classify(conn.downlink, conn.effectiveType, conn.saveData);
      if (t) apply(t, 'api');
    });
  }

  /* ---- offline / online banner ---- */
  function banner(text, dotClass) {
    if (!document.body) return;
    var host = document.createElement('div');
    host.className = 'netbanner';
    host.setAttribute('role', 'status');
    var dot = document.createElement('span');
    dot.className = 'netbanner__dot ' + dotClass;
    dot.setAttribute('aria-hidden', 'true');
    var label = document.createElement('strong');
    label.textContent = text;
    host.appendChild(dot);
    host.appendChild(label);
    document.body.appendChild(host);
    window.setTimeout(function () {
      if (host.parentNode) host.parentNode.removeChild(host);
    }, 4000);
  }

  window.addEventListener('offline', function () {
    root.setAttribute('data-net-offline', '1');
    banner('Offline — showing the last saved copy', 'is-off');
  });
  window.addEventListener('online', function () {
    root.removeAttribute('data-net-offline');
    banner('Back online', 'is-on');
  });
  if (navigator.onLine === false) root.setAttribute('data-net-offline', '1');
})();
