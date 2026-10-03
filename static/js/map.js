/* ================================================================
   TERRA NOVA — 3D TERRAIN RENDERER
   Pure canvas, zero dependencies. Part 1: deterministic terrain +
   camera math (exported so tests can exercise it under node).
   ================================================================ */
var TNMap = (function () {
  'use strict';

  var GRID = 80;    // heightmap cells per side
  var SPAN = 1.2;   // world covers -SPAN..SPAN on x/z

  /* ---------- seeded PRNG + value noise ---------- */
  function mulberry32(seed) {
    return function () {
      seed |= 0;
      seed = (seed + 0x6D2B79F5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function makeValueNoise(rand, size) {
    var grid = new Float32Array(size * size);
    for (var i = 0; i < grid.length; i++) grid[i] = rand();
    return function (x, y) {
      var xi = Math.floor(x), yi = Math.floor(y);
      var xf = x - xi, yf = y - yi;
      var sx = xf * xf * (3 - 2 * xf), sy = yf * yf * (3 - 2 * yf);
      var x0 = ((xi % size) + size) % size, y0 = ((yi % size) + size) % size;
      var x1 = (x0 + 1) % size, y1 = (y0 + 1) % size;
      var a = grid[y0 * size + x0], b = grid[y0 * size + x1];
      var c = grid[y1 * size + x0], d = grid[y1 * size + x1];
      return a + (b - a) * sx + (c - a) * sy + (a - b - c + d) * sx * sy;
    };
  }

  function fbm(noise, x, y, octaves) {
    var amp = 0.5, sum = 0, norm = 0;
    for (var o = 0; o < octaves; o++) {
      sum += amp * noise(x, y);
      norm += amp;
      amp *= 0.55;
      x = x * 2.07 + 11.3;
      y = y * 2.07 + 7.7;
    }
    return sum / norm; // 0..1
  }

  /* ---------- continent shape: rasterised Africa outline ----------
     The mask is built from real coast polygons (mainland Africa +
     Madagascar) so the landmass reads unmistakably as the continent.
     World mapping:  x = -(lon - LON0) * K   (west = +x)
                     z =  (lat - LAT0) * K   (north = +z)
     which renders north-up / east-right at the default azimuth. Coast
     cells get a graded mask so the fbm shoreline noise can nibble the
     polygon edge into a ragged, natural coastline. */
  var LON0 = 16.935, LAT0 = 1.255, K = 0.0288;

  function toWorld(poly) {
    var out = [];
    for (var i = 0; i < poly.length; i++) {
      out.push([-(poly[i][0] - LON0) * K, (poly[i][1] - LAT0) * K]);
    }
    return out;
  }

  function inPoly(poly, x, z) {
    var inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], zi = poly[i][1], xj = poly[j][0], zj = poly[j][1];
      if ((zi > z) !== (zj > z) &&
          x < (xj - xi) * (z - zi) / (zj - zi) + xi) inside = !inside;
    }
    return inside;
  }

  function edgeDist(poly, x, z) {
    var best = 1e9;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], zi = poly[i][1];
      var dx = poly[j][0] - xi, dz = poly[j][1] - zi;
      var t = ((x - xi) * dx + (z - zi) * dz) / (dx * dx + dz * dz || 1e-9);
      t = t < 0 ? 0 : t > 1 ? 1 : t;
      var px = xi + t * dx - x, pz = zi + t * dz - z;
      var d = px * px + pz * pz;
      if (d < best) best = d;
    }
    return Math.sqrt(best);
  }

  /* mainland Africa, clockwise from the Strait of Gibraltar (lon, lat) */
  var AFRICA_GEO = [
    [-5.90, 35.85], [-5.30, 35.90], [-3.90, 35.20], [-2.10, 35.15], [-0.60, 35.75],
    [1.30, 36.50], [3.10, 36.80], [5.70, 36.90], [7.80, 36.90], [8.75, 36.95],
    [9.90, 37.34], [11.10, 37.05], [10.70, 36.20], [10.60, 35.80], [10.75, 34.70],
    [10.10, 34.05], [10.10, 33.70], [11.50, 33.20], [12.10, 32.90], [13.20, 32.90],
    [15.20, 32.45], [16.60, 31.35], [17.90, 30.45], [19.00, 30.35], [20.05, 32.10],
    [21.60, 32.80], [23.10, 32.20], [23.95, 32.10], [25.20, 31.60], [27.20, 31.40],
    [29.90, 31.25], [31.40, 31.50], [32.30, 31.30], [32.55, 31.25],
    /* Gulf of Suez — Sinai stays outside the polygon */
    [32.60, 30.00], [33.10, 28.60], [33.90, 27.30], [34.40, 26.20], [35.00, 25.20],
    [35.60, 23.90], [36.60, 22.50], [36.95, 22.00], [37.25, 20.50], [37.30, 19.60],
    [38.30, 18.00], [38.70, 17.20], [39.45, 15.60], [40.40, 14.90], [41.60, 13.70],
    [42.70, 13.00], [43.35, 12.60], [43.15, 11.60],
    /* Gulf of Aden + the Horn */
    [44.00, 11.25], [45.00, 10.45], [46.30, 10.70], [47.70, 11.00], [49.30, 11.40],
    [50.70, 11.60], [51.40, 11.85],
    /* Somali + Indian Ocean coast */
    [51.30, 10.40], [50.40, 9.00], [49.20, 7.00], [47.60, 4.60], [45.30, 2.00],
    [44.00, 1.10], [42.60, -0.40], [41.55, -1.60], [41.00, -2.30], [40.10, -3.20],
    [39.70, -4.10], [39.10, -5.10], [39.30, -6.80], [39.35, -10.30], [40.50, -10.65],
    [40.45, -12.50], [40.65, -14.50], [39.90, -16.20], [38.30, -17.40], [36.90, -17.90],
    [35.90, -18.80], [34.90, -19.90], [35.05, -21.50], [35.40, -23.90], [33.90, -25.30],
    [32.65, -25.95], [32.80, -27.00], [31.00, -29.90], [29.50, -31.40], [27.90, -33.05],
    [26.50, -33.75], [25.60, -34.05], [23.50, -34.40], [22.00, -34.10], [20.00, -34.83],
    [18.45, -34.35], [18.40, -33.90], [17.95, -32.70], [17.30, -31.00], [16.60, -29.30],
    [16.45, -28.60], [15.60, -27.70], [15.20, -26.60], [14.50, -23.00], [13.40, -20.50],
    [12.60, -18.90], [12.00, -18.40], [11.80, -17.20], [12.05, -15.80], [12.15, -15.20],
    [13.00, -13.00], [13.50, -12.30], [13.20, -10.70], [13.00, -9.40], [13.25, -8.80],
    [12.60, -7.40], [12.35, -6.05],
    /* Gulf of Guinea */
    [12.20, -5.50], [11.90, -4.80], [11.20, -4.00], [9.90, -3.40], [9.50, -2.00],
    [8.90, -1.00], [8.70, -0.60], [9.20, -0.10], [9.45, 0.40], [9.40, 1.10],
    [9.75, 2.00], [9.90, 3.00], [9.70, 4.05], [9.20, 4.15], [8.30, 4.80],
    [7.55, 4.45], [7.00, 4.35], [6.00, 4.30], [5.40, 5.30], [4.00, 6.20],
    [2.40, 6.35], [1.20, 6.10], [0.20, 5.50], [-1.00, 5.05], [-2.10, 4.75],
    [-3.40, 5.15], [-4.05, 5.30], [-5.50, 5.05], [-6.10, 4.95], [-7.70, 4.37],
    /* West African bulge */
    [-8.60, 4.60], [-9.50, 5.30], [-10.80, 6.30], [-11.50, 7.00], [-12.40, 7.70],
    [-13.25, 8.50], [-13.70, 9.50], [-14.50, 10.70], [-15.65, 11.85], [-16.30, 12.60],
    [-16.55, 13.60], [-16.75, 14.70], [-17.53, 14.75],
    /* Western Sahara + Morocco */
    [-17.10, 15.70], [-16.55, 16.45], [-16.30, 17.30], [-16.05, 18.10], [-16.45, 19.30],
    [-17.05, 20.80], [-16.75, 21.70], [-16.40, 22.20], [-15.95, 23.70], [-15.10, 24.60],
    [-14.50, 26.10], [-13.80, 27.00], [-12.90, 27.90], [-11.70, 28.55], [-10.60, 29.55],
    [-9.90, 30.05], [-9.65, 30.40], [-9.30, 31.40], [-9.25, 32.30], [-8.50, 33.20],
    [-7.60, 33.65], [-6.85, 34.05], [-6.40, 34.70],
  ];

  var MADAGASCAR_GEO = [
    [49.30, -12.00], [49.95, -13.05], [50.15, -14.45], [50.50, -15.40], [50.20, -16.05],
    [49.90, -17.05], [49.50, -18.20], [49.00, -19.55], [48.65, -20.55], [48.40, -21.60],
    [47.85, -22.80], [47.10, -24.10], [45.45, -25.30], [44.00, -25.05], [43.55, -24.00],
    [43.30, -22.50], [43.60, -21.40], [44.05, -20.20], [43.90, -19.00], [44.35, -18.00],
    [45.10, -16.85], [46.30, -15.70], [47.25, -14.85], [48.05, -13.60], [48.55, -12.95],
  ];

  var LAND_POLYS = [toWorld(AFRICA_GEO), toWorld(MADAGASCAR_GEO)];

  function landMask(x, z) {
    var m = 0;
    for (var p = 0; p < LAND_POLYS.length; p++) {
      var poly = LAND_POLYS[p];
      if (!inPoly(poly, x, z)) continue;
      var d = edgeDist(poly, x, z);
      var v = 0.42 + d / 0.18;      // coast → 0.42 (noise-eroded), inland → 1
      if (v > 1) v = 1;
      if (v > m) m = v;
    }
    return m;
  }

  /* ---------- palettes per sector climate ---------- */
  var PALETTES = {
    aurelia: { low: [92, 166, 92], mid: [47, 116, 80], high: [74, 104, 74] },
    vermilion: { low: [201, 133, 88], mid: [171, 78, 52], high: [122, 64, 56] },
    glasslands: { low: [188, 212, 224], mid: [222, 234, 243], high: [246, 251, 255] },
    pelagos: { low: [84, 180, 164], mid: [56, 143, 130], high: [176, 220, 208] },
  };
  var SAND = [216, 197, 142];
  var ROCK = [139, 128, 120];
  var SNOW = [235, 242, 248];
  var ORDER = ['aurelia', 'vermilion', 'glasslands', 'pelagos'];

  /* named ranges: [x, z, sigma, amplitude] in world units */
  var RELIEF = [
    [0.66, 0.87, 0.13, 0.34],    // Atlas Mts (Morocco)
    [-0.61, 0.22, 0.15, 0.40],   // Ethiopian highlands
    [-0.52, -0.07, 0.13, 0.22],  // East African plateau
    [-0.36, -0.89, 0.12, 0.30],  // Drakensberg (south)
    [-0.59, -0.13, 0.05, 0.25],  // Kilimanjaro spike
  ];

  function lerp3(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }

  function sectorBlend(weights, e) {
    // weighted palette ramp across the four climates
    var out = [0, 0, 0];
    for (var i = 0; i < 4; i++) {
      var p = PALETTES[ORDER[i]], w = weights[i];
      if (w <= 0) continue;
      var c = e < 0.5 ? lerp3(p.low, p.mid, e / 0.5)
                      : lerp3(p.mid, p.high, (e - 0.5) / 0.5);
      out[0] += c[0] * w; out[1] += c[1] * w; out[2] += c[2] * w;
    }
    return out;
  }


  /* ---------- heightmap + per-cell static colours ---------- */
  function buildTerrain(seed, grid) {
    var rand = mulberry32(seed);
    var n1 = makeValueNoise(rand, 64);
    var n2 = makeValueNoise(rand, 64);
    var n3 = makeValueNoise(rand, 64);
    var N = grid || GRID;
    var count = N * N;
    var h = new Float32Array(count);          // elevation 0..1 (0 = sea)
    var wts = new Float32Array(count * 4);    // climate weights
    var relief = new Uint8Array(count * 3);   // shaded colours
    var flat = new Uint8Array(count * 3);     // unshaded (relief off)
    var heat = new Uint8Array(count * 3);     // temperature tint (built later)
    var land = [];                            // indices of land cells

    var anchors = [
      [-0.16, 0.04],  // aurelia — Congo basin
      [0.06, -0.60],  // vermilion — Namib / Kalahari
      [0.12, 0.58],   // glasslands — Sahara
      [-0.57, -0.21], // pelagos — East African coast
    ];

    for (var r = 0; r < N; r++) {
      for (var c = 0; c < N; c++) {
        var idx = r * N + c;
        var x = (c / (N - 1)) * 2 * SPAN - SPAN;
        var z = (r / (N - 1)) * 2 * SPAN - SPAN;

        var mask = landMask(x, z);
        var coast = fbm(n1, x * 2.6 + 13.1, z * 2.6 + 7.7, 4);
        var field = mask + (coast - 0.5) * 0.55;

        // climate weights (inverse square distance to anchors)
        var wsum = 0, w4 = [0, 0, 0, 0];
        for (var a = 0; a < 4; a++) {
          var dx = x - anchors[a][0], dz = z - anchors[a][1];
          var w = 1 / (dx * dx + dz * dz + 0.055);
          w4[a] = w; wsum += w;
        }
        for (a = 0; a < 4; a++) wts[idx * 4 + a] = w4[a] / wsum;

        var e = 0;
        if (field > 0.30) {
          /* land/sea test uses the noisy field (ragged, eroded coast),
             but the height ramp follows the smooth polygon distance so
             shoreline cells stay on a low shelf instead of spiking into
             cliff towers next to the sea */
          var base = Math.min((mask - 0.30) / 0.45, 1);
          var ridgeRaw = fbm(n2, x * 3.3 + 4.2, z * 3.3 + 9.1, 4);
          var ridge = 1 - Math.abs(ridgeRaw * 2 - 1);       // ridged peaks
          var detail = fbm(n3, x * 9.5, z * 9.5, 3);
          e = base * 0.52 + base * ridge * (0.30 + 0.28 * detail);
          /* named ranges (Atlas, Ethiopian highlands, Kilimanjaro…)
             scaled by base so they rise out of the coastal plain */
          for (var b = 0; b < RELIEF.length; b++) {
            var rx = x - RELIEF[b][0], rz = z - RELIEF[b][1];
            e += RELIEF[b][3] * base * Math.exp(
              -(rx * rx + rz * rz) / (2 * RELIEF[b][2] * RELIEF[b][2]));
          }
          if (e > 1) e = 1;
        }
        h[idx] = e;
        if (e > 0.001) land.push(idx);

        // static colour: palette blend + shore sand + rock/snow by height
        var col = sectorBlend([wts[idx * 4], wts[idx * 4 + 1],
                               wts[idx * 4 + 2], wts[idx * 4 + 3]], e);
        if (e < 0.10) {
          col = lerp3(SAND, col, e / 0.10);
        }
        var glassW = wts[idx * 4 + 2];
        var snowLine = 0.74 - glassW * 0.45;  // Glasslands snowline drops
        if (e > snowLine) {
          col = lerp3(col, SNOW, Math.min((e - snowLine) / 0.2, 1));
        } else if (e > 0.48 && glassW < 0.45) {
          col = lerp3(col, ROCK, Math.min((e - 0.48) / 0.3, 1) * 0.85);
        }

        // hillshade with fixed sun (north-west, high)
        var hl = (c > 0 ? h[idx - 1] : e), hr = (c < N - 1 ? h[idx + 1] : e);
        var hu = (r > 0 ? h[idx - N] : e), hd = (r < N - 1 ? h[idx + N] : e);
        var gx = (hr - hl) * 14, gz = (hd - hu) * 14;
        var nl = 1 / Math.sqrt(gx * gx + gz * gz + 1);
        var dot = (0.55 * gx + 0.72 + 0.42 * gz) * nl;
        var shade = e > 0 ? 0.42 + 0.62 * Math.max(dot, 0) : 1;

        var o = idx * 3;
        for (var k = 0; k < 3; k++) {
          var v = Math.round(col[k] * shade);
          relief[o + k] = v > 255 ? 255 : v;
          var vf = Math.round(col[k]);
          flat[o + k] = vf > 255 ? 255 : vf;
        }
      }
    }
    return { N: N, h: h, wts: wts, relief: relief, flat: flat, heat: heat, land: land };
  }

  /* ---------- camera + projection ---------- */
  function makeCamera(az, el, dist, fov) {
    var ce = Math.cos(el), se = Math.sin(el);
    var eye = [dist * ce * Math.sin(az), dist * se, dist * ce * Math.cos(az)];
    var fwd = [-eye[0], -eye[1], -eye[2]];
    var fl = Math.sqrt(fwd[0] * fwd[0] + fwd[1] * fwd[1] + fwd[2] * fwd[2]);
    fwd = [fwd[0] / fl, fwd[1] / fl, fwd[2] / fl];
    // right = normalize(fwd × worldUp)
    var right = [fwd[2], 0, -fwd[0]];
    var rl = Math.sqrt(right[0] * right[0] + right[2] * right[2]) || 1;
    right = [right[0] / rl, 0, right[2] / rl];
    // up = right × fwd
    var up = [
      right[1] * fwd[2] - right[2] * fwd[1],
      right[2] * fwd[0] - right[0] * fwd[2],
      right[0] * fwd[1] - right[1] * fwd[0],
    ];
    return { eye: eye, fwd: fwd, right: right, up: up, fov: fov };
  }

  function project(cam, w, h, x, y, z) {
    var rx = x - cam.eye[0], ry = y - cam.eye[1], rz = z - cam.eye[2];
    var depth = rx * cam.fwd[0] + ry * cam.fwd[1] + rz * cam.fwd[2];
    if (depth < 0.05) return null;
    var xs = rx * cam.right[0] + ry * cam.right[1] + rz * cam.right[2];
    var ys = rx * cam.up[0] + ry * cam.up[1] + rz * cam.up[2];
    var f = (h * 0.5) / Math.tan(cam.fov * 0.5);
    return { x: w * 0.5 + f * xs / depth, y: h * 0.5 - f * ys / depth, d: depth };
  }

  return {
    GRID: GRID, SPAN: SPAN, PALETTES: PALETTES,
    mulberry32: mulberry32, makeValueNoise: makeValueNoise, fbm: fbm,
    landMask: landMask, buildTerrain: buildTerrain,
    makeCamera: makeCamera, project: project,
  };
})();

if (typeof module !== 'undefined' && module.exports) {
  module.exports = TNMap;
}


/* ================================================================
   Part 2: DOM/canvas runtime (browser only)
   ================================================================ */
(function () {
  'use strict';
  if (typeof document === 'undefined') return;

  var scene = document.querySelector('[data-map]');
  var canvas = document.querySelector('[data-map-canvas]');
  if (!scene || !canvas || !canvas.getContext) return;

  var reduced = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- sector payload ---------- */
  var sectors = [];
  try {
    var blob = document.getElementById('tn-map-data');
    if (blob) sectors = JSON.parse(blob.textContent) || [];
  } catch (err) { sectors = []; }
  var byKey = {};
  sectors.forEach(function (s) { byKey[s.key] = s; });

  /* ---------- terrain + state ---------- */
  var T = window.TNMap || TNMap;
  var tier = '';
  try { tier = (document.cookie.match(/(?:^|;\s*)tn_net=([^;]+)/) || [])[1]; } catch (e) { /* private mode */ }
  if (tier !== 'lite' && tier !== 'balanced') tier = 'full';
  var lite = tier === 'lite';   // ≤ 512 kbps → essential-only scene
  var GRID_FULL = 80, GRID_LITE = 44;
  var terrain = T.buildTerrain(20261003, lite ? GRID_LITE : GRID_FULL);
  var N = terrain.N;
  var layers = { relief: true, routes: true, heat: false };

  var cam = { az: 0, el: 0.95, dist: 3.15, fov: 0.96 };
  var HOME = { az: 0, el: 0.95, dist: 3.15 };
  var dragging = false, lastX = 0, lastY = 0;
  var lastTouch = performance.now();
  var t0 = performance.now();

  /* ---------- heat colours from live temps ---------- */
  function lerp(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t,
            a[2] + (b[2] - a[2]) * t];
  }
  function heatStops(temp) {
    var t = Math.min(Math.max((temp + 15) / 60, 0), 1);
    var cold = [64, 120, 220], mild = [120, 200, 140];
    var warm = [255, 190, 80], hot = [235, 70, 50];
    if (t < 0.33) return lerp(cold, mild, t / 0.33);
    if (t < 0.66) return lerp(mild, warm, (t - 0.33) / 0.33);
    return lerp(warm, hot, (t - 0.66) / 0.34);
  }
  function buildHeat() {
    var keys = ['aurelia', 'vermilion', 'glasslands', 'pelagos'];
    var temps = keys.map(function (k) {
      return byKey[k] ? parseFloat(byKey[k].temp) : NaN;
    });
    if (temps.some(isNaN)) return;
    var stops = temps.map(heatStops);
    for (var i = 0; i < N * N; i++) {
      if (terrain.h[i] <= 0) continue;
      var c = [0, 0, 0];
      for (var a = 0; a < 4; a++) {
        var w = terrain.wts[i * 4 + a];
        c[0] += stops[a][0] * w; c[1] += stops[a][1] * w; c[2] += stops[a][2] * w;
      }
      var shade = terrain.relief[i * 3] / Math.max(terrain.flat[i * 3], 1);
      var o = i * 3;
      for (var k = 0; k < 3; k++) {
        var v = Math.round(c[k] * shade);
        terrain.heat[o + k] = v > 255 ? 255 : (v < 0 ? 0 : v);
      }
    }
  }
  buildHeat();

  /* live tier change (net.js fires terra:net) → rebuild the mesh */
  function setTier(next) {
    if (next !== 'lite' && next !== 'balanced') next = 'full';
    if (next === tier) return;
    tier = next;
    var wantLite = tier === 'lite';
    if (wantLite === lite) { kick(); return; }
    lite = wantLite;
    terrain = T.buildTerrain(20261003, lite ? GRID_LITE : GRID_FULL);
    N = terrain.N;
    buildHeat();
    kick();
  }
  document.addEventListener('terra:net', function (e) {
    setTier(e && e.detail ? e.detail.tier : 'full');
  });

  /* ---------- canvas sizing ---------- */
  var ctx = canvas.getContext('2d');
  var W = 0, H = 0, dpr = 1;
  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = scene.clientWidth; H = scene.clientHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* ---------- input: orbit / zoom / reset ---------- */
  scene.addEventListener('pointerdown', function (e) {
    if (e.target.closest('.map-toolbar') || e.target.closest('.pin')) return;
    dragging = true;
    lastX = e.clientX; lastY = e.clientY;
    scene.setPointerCapture(e.pointerId);
  });
  scene.addEventListener('pointermove', function (e) {
    if (!dragging) return;
    var dx = e.clientX - lastX, dy = e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    cam.az -= dx * 0.006;
    cam.el = Math.min(Math.max(cam.el + dy * 0.004, 0.22), 1.25);
    lastTouch = performance.now();
    kick();
  });
  function endDrag() { dragging = false; lastTouch = performance.now(); }
  scene.addEventListener('pointerup', endDrag);
  scene.addEventListener('pointercancel', endDrag);
  scene.addEventListener('wheel', function (e) {
    e.preventDefault();
    cam.dist = Math.min(Math.max(cam.dist + e.deltaY * 0.0022, 1.7), 5.4);
    lastTouch = performance.now();
    kick();
  }, { passive: false });
  scene.addEventListener('dblclick', function () {
    cam.az = HOME.az; cam.el = HOME.el; cam.dist = HOME.dist;
    lastTouch = performance.now();
    kick();
  });

  /* ---------- layer toolbar ---------- */
  document.querySelectorAll('.map-tool').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var name = btn.getAttribute('data-layer');
      layers[name] = !layers[name];
      btn.classList.toggle('is-on', layers[name]);
      btn.setAttribute('aria-pressed', String(layers[name]));
      kick();
    });
  });

  /* ---------- selection + HUD ---------- */
  var hud = {
    name: document.querySelector('[data-hud-name]'),
    cond: document.querySelector('[data-hud-cond]'),
    temp: document.querySelector('[data-hud-temp]'),
    feels: document.querySelector('[data-hud-feels]'),
    anom: document.querySelector('[data-hud-anom]'),
    hum: document.querySelector('[data-hud-hum]'),
    wind: document.querySelector('[data-hud-wind]'),
    wind2: document.querySelector('[data-hud-wind2]'),
    humBar: document.querySelector('[data-hud-humbars]'),
    windBar: document.querySelector('[data-hud-windbars]'),
    icon: document.querySelector('[data-hud-icon]'),
  };

  function setIcon(name) {
    if (!hud.icon) return;
    var src = document.querySelector('[data-wx-icon="' + name + '"]');
    if (src) hud.icon.innerHTML = src.innerHTML;
  }

  function pick(getName) {
    var s = byKey[getName];
    var el = document.querySelector('.pin[data-sector="' + getName + '"]');
    return function (jsonKey, attrKey, transform) {
      var raw;
      if (s && s[jsonKey] !== undefined && s[jsonKey] !== null) raw = s[jsonKey];
      else if (el) raw = el.getAttribute(attrKey || jsonKey);
      if (raw === undefined || raw === null || raw === '') return null;
      return transform ? transform(raw) : raw;
    };
  }

  function selectSector(key) {
    if (!byKey[key] && !document.querySelector('[data-sector="' + key + '"]')) return;
    var g = pick(key);
    var num = function (v) { var f = parseFloat(v); return isNaN(f) ? null : f; };

    if (hud.name) hud.name.textContent = g('name', 'data-name') || key;
    if (hud.cond) hud.cond.textContent =
      g('condition', 'data-cond') || g('cond') || '';
    var temp = num(g('temp'));
    if (hud.temp) hud.temp.textContent = temp !== null ? temp : '—';
    var feels = num(g('feels'));
    if (hud.feels) hud.feels.textContent = feels !== null ? feels : '—';
    var anom = num(g('anomaly', 'data-anom'));
    if (hud.anom) {
      hud.anom.textContent = anom === null ? ''
        : (anom >= 0 ? '+' : '') + anom.toFixed(1) + '°C ABOVE SEASONAL';
    }
    var hum = num(g('humidity', 'data-hum'));
    if (hud.hum && hum !== null) hud.hum.textContent = hum;
    var wind = num(g('wind'));
    if (hud.wind && wind !== null) hud.wind.textContent = wind;
    if (hud.wind2 && wind !== null) hud.wind2.textContent = wind;
    if (hud.humBar && hum !== null) hud.humBar.style.setProperty('--w', hum + '%');
    if (hud.windBar && wind !== null) {
      hud.windBar.style.setProperty('--w', Math.min(wind / 40 * 100, 100) + '%');
    }
    setIcon(g('icon', 'data-icon') || 'sun');

    document.querySelectorAll('[data-sector]').forEach(function (el) {
      el.classList.toggle('is-active', el.getAttribute('data-sector') === key);
    });
    lastTouch = performance.now();
    kick();
  }

  document.querySelectorAll('[data-sector]').forEach(function (el) {
    el.addEventListener('click', function () {
      selectSector(el.getAttribute('data-sector'));
    });
  });
  if (sectors.length) selectSector(sectors[0].key);


  /* ---------- scene furniture: clouds, stars, routes ---------- */
  var srand = T.mulberry32(777);
  var clouds = [];
  for (var ci = 0; ci < 14; ci++) {
    clouds.push({
      x: (srand() * 2 - 1) * 1.3,
      z: (srand() * 2 - 1) * 1.3,
      alt: 0.30 + srand() * 0.30,
      scale: 0.09 + srand() * 0.15,
      speed: 0.010 + srand() * 0.016,
    });
  }
  var stars = [];
  for (ci = 0; ci < 70; ci++) {
    stars.push({ x: srand(), y: srand() * 0.55, r: 0.4 + srand() * 1.1,
                 a: 0.25 + srand() * 0.6, p: srand() * 6.28 });
  }
  var ROUTES = [
    ['aurelia', 'vermilion'], ['aurelia', 'glasslands'],
    ['aurelia', 'pelagos'], ['vermilion', 'pelagos'],
    ['pelagos', 'glasslands'],
  ];
  var SPAN = T.SPAN, HSCALE = 0.26;
  var FOG = [16, 44, 82];

  function heightAt(x, z) {
    var fx = (x + SPAN) / (2 * SPAN) * (N - 1);
    var fz = (z + SPAN) / (2 * SPAN) * (N - 1);
    var c = Math.min(Math.max(Math.round(fx), 0), N - 1);
    var r = Math.min(Math.max(Math.round(fz), 0), N - 1);
    return terrain.h[r * N + c];
  }

  /* ---------- draw passes ---------- */
  function drawSky(time) {
    var g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#060e20');
    g.addColorStop(0.55, '#0a1a33');
    g.addColorStop(1, '#0e2745');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);

    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var tw = reduced ? 1 : 0.7 + 0.3 * Math.sin(time * 1.4 + s.p);
      ctx.globalAlpha = s.a * tw;
      ctx.fillStyle = '#cfe4ff';
      ctx.beginPath();
      ctx.arc(s.x * W, s.y * H, s.r, 0, 6.2832);
      ctx.fill();
    }
    ctx.globalAlpha = 1;

    var sx = W * 0.24, sy = H * 0.16;               // sun over the NW range
    var glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, W * 0.19);
    glow.addColorStop(0, 'rgba(255, 224, 170, .95)');
    glow.addColorStop(0.14, 'rgba(255, 196, 120, .55)');
    glow.addColorStop(1, 'rgba(255, 178, 87, 0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H * 0.6);
    ctx.fillStyle = '#fff3dd';
    ctx.beginPath();
    ctx.arc(sx, sy, W * 0.016, 0, 6.2832);
    ctx.fill();
  }

  function horizonY(cam) {
    var best = H;
    for (var i = 0; i < 180; i++) {
      var th = i / 180 * 6.2832;
      var p = T.project(cam, W, H, Math.cos(th) * 400, 0, Math.sin(th) * 400);
      if (p && p.y < best) best = p.y;
    }
    return Math.max(best, 0);
  }

  function drawOcean(cam, time) {
    var hy = horizonY(cam);
    var g = ctx.createLinearGradient(0, hy, 0, H);
    g.addColorStop(0, '#12406e');
    g.addColorStop(0.35, '#0c2c55');
    g.addColorStop(1, '#061530');
    ctx.fillStyle = g;
    ctx.fillRect(0, hy, W, H - hy);

    // animated swell lines
    ctx.lineWidth = 1;
    for (var k = 0; k < 18; k++) {
      var z = -1.5 + k * 0.18 + (reduced ? 0 : Math.sin(time * 0.5 + k * 0.9) * 0.02);
      var alpha = 0.03 + 0.10 * (k / 18);
      var started = false, maxD = 0;
      ctx.strokeStyle = 'rgba(155, 215, 255, ' + alpha.toFixed(3) + ')';
      ctx.beginPath();
      for (var x = -1.7; x <= 1.7001; x += 0.14) {
        var p = T.project(cam, W, H, x, 0.004, z);
        if (!p) { started = false; continue; }
        if (p.y < hy - 1 || p.y > H + 4) { started = false; continue; }
        if (!started) { ctx.moveTo(p.x, p.y); started = true; }
        else ctx.lineTo(p.x, p.y);
        if (p.d > maxD) maxD = p.d;
      }
      ctx.stroke();
    }
  }

  var depths = new Float32Array(0);
  var order = [];
  function drawTerrain(cam) {
    var table = layers.heat ? terrain.heat : (layers.relief ? terrain.relief : terrain.flat);
    var land = terrain.land;
    if (depths.length < land.length) depths = new Float32Array(land.length);
    order.length = 0;

    for (var i = 0; i < land.length; i++) {
      var idx = land[i];
      var r = (idx / N) | 0, c = idx - r * N;
      var x = (c / (N - 1)) * 2 * SPAN - SPAN;
      var z = (r / (N - 1)) * 2 * SPAN - SPAN;
      var y = terrain.h[idx] * HSCALE;
      var rx = x - cam.eye[0], ry = y - cam.eye[1], rz = z - cam.eye[2];
      var d = rx * cam.fwd[0] + ry * cam.fwd[1] + rz * cam.fwd[2];
      depths[i] = d;
      if (d >= 0.05) order.push(i);
    }
    order.sort(function (a, b) { return depths[b] - depths[a]; });

    var cell = (2 * SPAN) / (N - 1);
    for (var oi = 0; oi < order.length; oi++) {
      i = order[oi];
      idx = land[i];
      r = (idx / N) | 0; c = idx - r * N;
      var x0 = (c / (N - 1)) * 2 * SPAN - SPAN;
      var z0 = (r / (N - 1)) * 2 * SPAN - SPAN;
      var h00 = terrain.h[idx] * HSCALE;
      var h10 = (c < N - 1 ? terrain.h[idx + 1] : terrain.h[idx]) * HSCALE;
      var h01 = (r < N - 1 ? terrain.h[idx + N] : terrain.h[idx]) * HSCALE;
      var h11 = (c < N - 1 && r < N - 1 ? terrain.h[idx + N + 1]
                 : terrain.h[idx]) * HSCALE;

      var p1 = T.project(cam, W, H, x0, h00, z0);
      var p2 = T.project(cam, W, H, x0 + cell, h10, z0);
      var p3 = T.project(cam, W, H, x0 + cell, h11, z0 + cell);
      var p4 = T.project(cam, W, H, x0, h01, z0 + cell);
      if (!p1 || !p2 || !p3 || !p4) continue;

      var d = depths[i];
      var fog = Math.min(Math.max((d - 1.5) * 0.16, 0), 0.72);
      var o = idx * 3;
      var rr = Math.round(table[o] + (FOG[0] - table[o]) * fog);
      var gg = Math.round(table[o + 1] + (FOG[1] - table[o + 1]) * fog);
      var bb = Math.round(table[o + 2] + (FOG[2] - table[o + 2]) * fog);
      ctx.fillStyle = 'rgb(' + rr + ',' + gg + ',' + bb + ')';

      ctx.beginPath();
      ctx.moveTo(p1.x, p1.y);
      ctx.lineTo(p2.x, p2.y);
      ctx.lineTo(p3.x, p3.y);
      ctx.lineTo(p4.x, p4.y);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();  // same colour closes seams between quads
    }
  }


  function drawRoutes(cam, time) {
    if (!layers.routes || !sectors.length) return;
    ctx.lineCap = 'round';
    for (var ri = 0; ri < ROUTES.length; ri++) {
      var A = byKey[ROUTES[ri][0]], B = byKey[ROUTES[ri][1]];
      if (!A || !B) continue;
      ctx.setLineDash([]);
      drawRouteLine(cam, A, B, 7, 'rgba(255, 178, 87, .16)', false);
      ctx.setLineDash([7, 9]);
      ctx.lineDashOffset = reduced ? 0 : -time * 26;
      drawRouteLine(cam, A, B, 1.6, 'rgba(255, 214, 150, .9)', true);
      ctx.setLineDash([]);
      ctx.lineDashOffset = 0;
    }
  }

  function drawRouteLine(cam, A, B, width, color, onlyVisible) {
    var pts = 26, started = false, drew = 0;
    ctx.lineWidth = width;
    ctx.strokeStyle = color;
    ctx.beginPath();
    for (var i = 0; i <= pts; i++) {
      var t = i / pts;
      var x = A.wx + (B.wx - A.wx) * t;
      var z = A.wy + (B.wy - A.wy) * t;
      var y = heightAt(x, z) * HSCALE + 0.035;
      var p = T.project(cam, W, H, x, y, z);
      if (!p) { started = false; continue; }
      if (!started) { ctx.moveTo(p.x, p.y); started = true; }
      else ctx.lineTo(p.x, p.y);
      drew++;
    }
    if (onlyVisible && drew < 2) return;
    ctx.stroke();
  }

  function drawGlows(cam, time) {
    var tints = {
      aurelia: '127, 240, 192', vermilion: '255, 140, 90',
      glasslands: '155, 215, 255', pelagos: '94, 230, 210',
    };
    for (var i = 0; i < sectors.length; i++) {
      var s = sectors[i];
      var y = heightAt(s.wx, s.wy) * HSCALE + 0.02;
      var p = T.project(cam, W, H, s.wx, y, s.wy);
      if (!p) continue;
      var pulse = reduced ? 0.75 : 0.62 + 0.38 * Math.sin(time * 1.6 + i * 1.7);
      var rad = Math.max(26, 120 / Math.max(p.d, 0.5));
      var tint = tints[s.key] || '255, 178, 87';
      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, rad);
      g.addColorStop(0, 'rgba(' + tint + ',' + (0.34 * pulse).toFixed(3) + ')');
      g.addColorStop(1, 'rgba(' + tint + ', 0)');
      ctx.fillStyle = g;
      ctx.fillRect(p.x - rad, p.y - rad, rad * 2, rad * 2);
    }
  }

  function drawClouds(cam, time) {
    var maxClouds = lite ? Math.min(6, clouds.length) : clouds.length;
    for (var i = 0; i < maxClouds; i++) {
      var c = clouds[i];
      if (!reduced) {
        c.x += c.speed * 0.016;
        if (c.x > 1.35) c.x = -1.35;
      }
      var p = T.project(cam, W, H, c.x, c.alt, c.z);
      if (!p) continue;
      var rad = Math.max(14, c.scale * 320 / Math.max(p.d, 0.6));
      var g = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, rad);
      g.addColorStop(0, 'rgba(226, 238, 252, .30)');
      g.addColorStop(0.6, 'rgba(210, 226, 246, .12)');
      g.addColorStop(1, 'rgba(200, 220, 245, 0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.ellipse(p.x, p.y, rad, rad * 0.44, 0, 0, 6.2832);
      ctx.fill();
    }
  }


  /* ---------- DOM beacons follow the projected anchors ---------- */
  var pinEls = Array.prototype.slice.call(document.querySelectorAll('.pin'));
  function placeBeacons(cam) {
    for (var i = 0; i < pinEls.length; i++) {
      var el = pinEls[i];
      var wx = parseFloat(el.getAttribute('data-wx'));
      var wy = parseFloat(el.getAttribute('data-wy'));
      if (isNaN(wx) || isNaN(wy)) { el.classList.add('is-hidden'); continue; }
      var y = heightAt(wx, wy) * HSCALE + 0.05;
      var p = T.project(cam, W, H, wx, y, wy);
      var inside = p && p.x > -40 && p.x < W + 40 && p.y > -40 && p.y < H + 40;
      el.classList.toggle('is-hidden', !inside);
      if (inside) {
        el.style.left = p.x.toFixed(1) + 'px';
        el.style.top = p.y.toFixed(1) + 'px';
      }
    }
  }

  /* ---------- readout + compass ---------- */
  var readout = document.querySelector('[data-map-readout]');
  var needle = document.querySelector('[data-compass-needle]');
  function updateChrome(camera) {
    if (readout) {
      var azDeg = ((cam.az * 180 / Math.PI) % 360 + 360) % 360;
      var zoom = Math.round((5.4 - cam.dist) / (5.4 - 1.7) * 60 + 70);
      readout.textContent = 'AZ ' +
        ('00' + Math.round(azDeg)).slice(-3) + '° · EL ' +
        Math.round(cam.el * 180 / Math.PI) + '° · ZOOM ' + zoom + '%';
    }
    if (needle && camera) {
      var o = T.project(camera, W, H, 0, 0, 0);
      var n = T.project(camera, W, H, 0, 0, -1);   // world north is −z
      if (o && n) {
        var ang = Math.atan2(n.x - o.x, -(n.y - o.y));
        needle.style.setProperty('--az',
          (ang * 180 / Math.PI).toFixed(1) + 'deg');
      }
    }
  }

  /* ---------- frame loop ---------- */
  var rafId = 0, visible = true;
  function frame(now) {
    rafId = 0;
    if (!visible) return;
    var time = (now - t0) / 1000;

    if (!reduced && !lite && !dragging && now - lastTouch > 2600) {
      cam.az += 0.008;                 // slow idle drift
    }
    var camera = T.makeCamera(cam.az, cam.el, cam.dist, cam.fov);
    ctx.clearRect(0, 0, W, H);
    drawSky(time);
    drawOcean(camera, time);
    drawTerrain(camera);
    drawRoutes(camera, time);
    drawGlows(camera, time);
    drawClouds(camera, time);
    placeBeacons(camera);
    updateChrome(camera);

    if (!reduced && !lite) rafId = requestAnimationFrame(frame);
  }

  function kick() {
    if (!visible || rafId) return;
    rafId = requestAnimationFrame(frame);
  }

  /* ---------- lifecycle ---------- */
  window.addEventListener('resize', function () { resize(); kick(); });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) kick();
  });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        visible = true;
        kick();
      } else {
        visible = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
      }
    }, { threshold: 0.02 }).observe(scene);
  }

  resize();
  kick();
})();

