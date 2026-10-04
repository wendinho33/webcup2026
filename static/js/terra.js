/* TERRA NOVA — interactions */
(function () {
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var motionReduced = function () {
    return reduced ||
      document.documentElement.getAttribute('data-motion') === 'reduce';
  };

  /* ---------------- nav ---------------- */
  var nav = document.querySelector('[data-nav]');
  if (nav) {
    var onScroll = function () {
      nav.classList.toggle('is-scrolled', window.scrollY > 14);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    var toggle = document.querySelector('[data-menu-toggle]');
    if (toggle) {
      var setOpen = function (open) {
        nav.classList.toggle('is-open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      };
      toggle.addEventListener('click', function () {
        setOpen(!nav.classList.contains('is-open'));
      });
      document.querySelectorAll('[data-nav-links] a').forEach(function (link) {
        link.addEventListener('click', function () { setOpen(false); });
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { setOpen(false); }
      });
      document.addEventListener('click', function (e) {
        if (nav.classList.contains('is-open') && !nav.contains(e.target)) {
          setOpen(false);
        }
      });
    }
  }

  /* ---------------- starfield ---------------- */
  var canvas = document.getElementById('starfield');
  if (canvas && canvas.getContext) {
    var ctx = canvas.getContext('2d');
    var stars = [];
    var w = 0, h = 0;
    var mouseX = 0, mouseY = 0, curX = 0, curY = 0;
    var shooting = null;
    var nextShot = 3500;
    var rafId = null;
    var last = 0;

    var resize = function () {
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = canvas.clientWidth || window.innerWidth;
      h = canvas.clientHeight || window.innerHeight;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      var count = Math.max(90, Math.min(280, Math.round((w * h) / 6400)));
      stars = [];
      for (var i = 0; i < count; i++) {
        stars.push({
          x: Math.random() * w,
          y: Math.random() * h,
          r: Math.random() * 1.25 + 0.3,
          a: Math.random() * 0.55 + 0.3,
          tw: Math.random() * Math.PI * 2,
          sp: Math.random() * 0.85 + 0.15,
          ice: Math.random() < 0.14
        });
      }
    };

    var spawnShooting = function () {
      var fromLeft = Math.random() < 0.5;
      shooting = {
        x: fromLeft ? -60 : w + 60,
        y: Math.random() * h * 0.5,
        vx: (fromLeft ? 1 : -1) * (5.5 + Math.random() * 3),
        vy: 1.6 + Math.random() * 1.6,
        life: 1
      };
    };

    var draw = function (dt, t) {
      ctx.clearRect(0, 0, w, h);

      if (!reduced) {
        curX += (mouseX - curX) * 0.04;
        curY += (mouseY - curY) * 0.04;
      }

      for (var i = 0; i < stars.length; i++) {
        var s = stars[i];
        var twinkle = reduced ? 1 : (0.62 + 0.38 * Math.sin(t * 0.0016 * s.sp * 4 + s.tw));
        var ox = curX * s.sp * 16;
        var oy = curY * s.sp * 11;
        ctx.globalAlpha = Math.max(0, s.a * twinkle);
        ctx.fillStyle = s.ice ? '#9bd7ff' : '#eaf2ff';
        ctx.beginPath();
        ctx.arc(s.x + ox, s.y + oy, s.r, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.globalAlpha = 1;

      if (!reduced) {
        nextShot -= dt;
        if (!shooting && nextShot <= 0) {
          spawnShooting();
          nextShot = 6000 + Math.random() * 9000;
        }
        if (shooting) {
          shooting.x += shooting.vx * dt * 0.06;
          shooting.y += shooting.vy * dt * 0.06;
          shooting.life -= dt * 0.0011;
          if (shooting.life <= 0 ||
              shooting.x < -120 || shooting.x > w + 120 ||
              shooting.y > h + 120) {
            shooting = null;
          } else {
            var tx = shooting.x - shooting.vx * 14;
            var ty = shooting.y - shooting.vy * 14;
            var grad = ctx.createLinearGradient(shooting.x, shooting.y, tx, ty);
            grad.addColorStop(0, 'rgba(255,255,255,' + (0.85 * shooting.life) + ')');
            grad.addColorStop(1, 'rgba(155,215,255,0)');
            ctx.strokeStyle = grad;
            ctx.lineWidth = 1.6;
            ctx.beginPath();
            ctx.moveTo(shooting.x, shooting.y);
            ctx.lineTo(tx, ty);
            ctx.stroke();
          }
        }
      }
    };

    var loop = function (now) {
      var dt = Math.min(50, now - last || 16);
      last = now;
      draw(dt, now);
      rafId = window.requestAnimationFrame(loop);
    };

    resize();
    window.addEventListener('resize', function () {
      resize();
      if (motionReduced()) draw(16, 0);
    });

    if (motionReduced()) {
      draw(16, 0);
    } else {
      window.addEventListener('mousemove', function (e) {
        mouseX = (e.clientX / (w || 1) - 0.5) * 2;
        mouseY = (e.clientY / (h || 1) - 0.5) * 2;
      }, { passive: true });

      rafId = window.requestAnimationFrame(loop);
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
          if (rafId) { window.cancelAnimationFrame(rafId); rafId = null; }
        } else if (!rafId && !motionReduced()) {
          last = 0;
          rafId = window.requestAnimationFrame(loop);
        }
      });
    }
  }
  /* ---------------- accessibility: manual reduce-motion ---------------- */
  document.addEventListener('terra:a11y-change', function (event) {
    if (!canvas || !canvas.getContext || reduced) return;
    var off = !!(event.detail && event.detail.motion);
    if (off && rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = null;
      draw(16, 0);
    } else if (!off && !rafId && !document.hidden) {
      last = 0;
      rafId = window.requestAnimationFrame(loop);
    }
  });

  /* ---------------- shared reveal observer ---------------- */
  var revealables = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
  if ('IntersectionObserver' in window && !motionReduced()) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px -6% 0px' });
    revealables.forEach(function (el) { observer.observe(el); });
  } else {
    revealables.forEach(function (el) { el.classList.add('is-in'); });
  }

  /* ---------------- count-up stats ---------------- */
  document.querySelectorAll('[data-count]').forEach(function (el) {
    var target = parseFloat(el.getAttribute('data-count'));
    if (isNaN(target)) return;
    var decimals = parseInt(el.getAttribute('data-decimals') || '0', 10);
    if (motionReduced()) { el.textContent = target.toFixed(decimals); return; }

    var play = function () {
      var start = null;
      var duration = 1500;
      var step = function (now) {
        if (start === null) start = now;
        var p = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = (target * eased).toFixed(decimals);
        if (p < 1) window.requestAnimationFrame(step);
      };
      window.requestAnimationFrame(step);
    };

    if ('IntersectionObserver' in window) {
      var once = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) { play(); once.unobserve(el); }
        });
      }, { threshold: 0.4 });
      once.observe(el);
    } else {
      play();
    }
  });

  /* ---------------- departure countdown ---------------- */
  var cd = document.querySelector('[data-countdown]');
  if (cd) {
    var target = new Date(cd.getAttribute('data-countdown')).getTime();
    var dEl = cd.querySelector('[data-cd="d"]');
    var hEl = cd.querySelector('[data-cd="h"]');
    var mEl = cd.querySelector('[data-cd="m"]');
    var sEl = cd.querySelector('[data-cd="s"]');
    var pad = function (n) { return n < 10 ? '0' + n : String(n); };

    var tick = function () {
      var diff = Math.max(0, target - Date.now());
      var secs = Math.floor(diff / 1000);
      if (dEl) dEl.textContent = String(Math.floor(secs / 86400));
      if (hEl) hEl.textContent = pad(Math.floor(secs / 3600) % 24);
      if (mEl) mEl.textContent = pad(Math.floor(secs / 60) % 60);
      if (sEl) sEl.textContent = pad(secs % 60);
    };
    tick();
    window.setInterval(tick, 1000);
  }

  /* ---------------- toast dismissal ---------------- */
  document.querySelectorAll('.toast').forEach(function (toast, index) {
    window.setTimeout(function () {
      toast.classList.add('is-out');
      window.setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 450);
    }, 4600 + index * 500);
  });
})();
