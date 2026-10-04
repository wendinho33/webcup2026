"""Pure-SVG chart primitives for the Terra Nova admin control deck.

No JavaScript and no CDN: every chart is a small, accessible <svg> with a
root <title> plus per-element <title> tooltips, so operators get exact
values on hover and screen readers get a label. Palette and type follow the
Terra Nova design system (void / solar / mint / ice).
"""

import math

from django.utils.html import escape
from django.utils.safestring import mark_safe

SOLAR = '#f59e0b'
SOLAR2 = '#ea580c'
MINT = '#10b981'
ICE = '#0284c7'
DIM = '#94a3b8'
GRID = 'rgba(15, 23, 42, .08)'
TRACK = 'rgba(15, 23, 42, .05)'

SEVERITY_COLORS = {'elevated': ICE, 'high': SOLAR, 'extreme': SOLAR2}


def fmt_num(v):
    """Exact, grouped number label: 1234 -> '1,234', 2.5 -> '2.5'."""
    f = float(v or 0)
    return f'{int(f):,}' if f == int(f) else f'{f:,.1f}'


def nice_max(v):
    """Round a chart ceiling up to 1/2/2.5/5 × 10^k for clean gridlines."""
    if v <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(v))
    for mult in (1, 2, 2.5, 5, 10):
        if v <= mult * base:
            return float(mult * base)
    return float(10 * base)


def _y_grid(top, left, right, top_pad, plot_h, width):
    """Horizontal gridlines + y-axis labels at 0 / 50 / 100% of top."""
    out = ''
    for frac in (0, 0.5, 1):
        y = top_pad + plot_h * (1 - frac)
        out += (
            f'<line x1="{left}" y1="{y:.1f}" x2="{right}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-dasharray="2 5"/>'
            f'<text x="{left - 7}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="tn-axis">{fmt_num(top * frac)}</text>'
        )
    return out


def sparkline(values, color=MINT, width=134, height=38, label='trend'):
    """Tiny KPI trend line with an exact-value tooltip."""
    vals = [float(v or 0) for v in values] or [0.0]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    dx = width / max(len(vals) - 1, 1)
    pts = [
        (i * dx, height - 4 - (v - lo) / span * (height - 11))
        for i, v in enumerate(vals)
    ]
    line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in pts)
    title = f'{label}: latest {fmt_num(vals[-1])}, peak {fmt_num(hi)} over {len(vals)} days'
    return mark_safe(
        f'<svg class="tn-spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(title)}"><title>{escape(title)}</title>'
        f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.7" fill="{color}"/>'
        f'</svg>'
    )


def area_chart(labels, values, label, color=SOLAR, height=172, gid='tn-g1'):
    """Time-series area chart with gradient fill and per-point tooltips."""
    width, left, right, top_pad, bottom = 560, 42, 12, 16, 26
    plot_w = width - left - right
    plot_h = height - top_pad - bottom
    vals = [float(v or 0) for v in values] or [0.0]
    n = len(vals)
    top = nice_max(max(vals))
    dx = plot_w / max(n - 1, 1)
    base_y = top_pad + plot_h

    pts = [
        (left + i * dx, base_y - (v / top) * plot_h) for i, v in enumerate(vals)
    ]
    line = ' M '.join(f'{x:.1f} {y:.1f}' for x, y in pts)
    area = (
        f'M {pts[0][0]:.1f} {pts[0][1]:.1f} L '
        + ' L '.join(f'{x:.1f} {y:.1f}' for x, y in pts[1:])
        + f' L {pts[-1][0]:.1f} {base_y:.1f} L {pts[0][0]:.1f} {base_y:.1f} Z'
    )
    grid = _y_grid(top, left, width - right, top_pad, plot_h, width)
    x_labels = ''
    for i in sorted({0, n // 2, n - 1}):
        if 0 <= i < len(labels):
            x_labels += (
                f'<text x="{pts[i][0]:.1f}" y="{height - 7}" text-anchor="middle" '
                f'class="tn-axis">{escape(str(labels[i]))}</text>'
            )
    dots = ''.join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.4" fill="{color}">'
        f'<title>{escape(str(labels[i]))}: {fmt_num(vals[i])}</title></circle>'
        for i, (x, y) in enumerate(pts)
    )
    return mark_safe(
        f'<svg class="tn-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity=".36"/>'
        f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>'
        f'{grid}<path d="{area}" fill="url(#{gid})"/>'
        f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>{dots}{x_labels}</svg>'
    )


def bar_chart(items, label, color=MINT, height=176):
    """Vertical bar chart; items = [(label, value), …]."""
    width, left, right, top_pad, bottom = 560, 42, 12, 20, 30
    plot_w = width - left - right
    plot_h = height - top_pad - bottom
    vals = [float(v) for _, v in items] or [0.0]
    top = nice_max(max(vals))
    n = max(len(items), 1)
    slot = plot_w / n
    bar_w = slot * 0.56
    base_y = top_pad + plot_h
    grid = _y_grid(top, left, width - right, top_pad, plot_h, width)
    bars = ''
    for i, (lab, v) in enumerate(items):
        cx = left + slot * (i + 0.5)
        bh = (float(v) / top) * plot_h
        y = base_y - bh
        bars += (
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{max(bh, 1.5):.1f}" rx="3" fill="{color}" opacity=".9">'
            f'<title>{escape(str(lab))}: {fmt_num(v)}</title></rect>'
        )
        if n <= 8 or i % 2 == 0:
            bars += (
                f'<text x="{cx:.1f}" y="{height - 9}" text-anchor="middle" '
                f'class="tn-axis">{escape(str(lab))}</text>'
            )
        if n <= 7 and v:
            bars += (
                f'<text x="{cx:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                f'class="tn-val">{fmt_num(v)}</text>'
            )
    return mark_safe(
        f'<svg class="tn-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f'{grid}{bars}</svg>'
    )


def donut(segments, center_value, center_label, size=176):
    """Stroke-based donut; segments = [(label, value, color), …]."""
    r = size / 2 - 15
    c = size / 2
    circ = 2 * math.pi * r
    total = sum(v for _, v, _ in segments) or 0
    out = (
        f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{TRACK}" '
        f'stroke-width="17"/>'
    )
    offset = 0.0
    for name, v, col in segments:
        frac = (v / total) if total else 0.0
        dash = max(frac * circ - 3.5, 0.0)
        out += (
            f'<circle cx="{c}" cy="{c}" r="{r}" fill="none" stroke="{col}" '
            f'stroke-width="17" stroke-dasharray="{dash:.1f} {circ - dash:.1f}" '
            f'stroke-dashoffset="{-offset:.1f}" transform="rotate(-90 {c} {c})">'
            f'<title>{escape(name)}: {fmt_num(v)} ({frac * 100:.0f}%)</title></circle>'
        )
        offset += frac * circ
    out += (
        f'<text x="{c}" y="{c - 1}" text-anchor="middle" class="tn-donut-v">'
        f'{escape(str(center_value))}</text>'
        f'<text x="{c}" y="{c + 19}" text-anchor="middle" class="tn-donut-l">'
        f'{escape(str(center_label))}</text>'
    )
    return mark_safe(
        f'<svg class="tn-donut" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="{escape(str(center_label))}: {escape(str(center_value))}">'
        f'<title>{escape(str(center_label))}: {escape(str(center_value))}</title>'
        f'{out}</svg>'
    )


def hbars(items, label, width=560, row_h=34):
    """Horizontal bars with track background; items = [(label, value, color)].

    Used for ordered pipelines where labels are long (civic stages, ticket
    states) — value printed at the right end, exact count in each tooltip.
    """
    if not items:
        items = [('—', 0, ICE)]
    left, right = 148, 52
    plot_w = width - left - right
    top = max(v for _, v, _ in items) or 1
    height = len(items) * row_h + 4
    rows = ''
    for i, (lab, v, col) in enumerate(items):
        y = i * row_h + 4
        w = max(float(v) / top * plot_w, 2.5)
        rows += (
            f'<text x="{left - 12}" y="{y + 17}" text-anchor="end" '
            f'class="tn-hbar-l">{escape(str(lab))}</text>'
            f'<rect x="{left}" y="{y + 5}" width="{plot_w}" height="17" rx="8.5" '
            f'fill="{TRACK}"/>'
            f'<rect x="{left}" y="{y + 5}" width="{w:.1f}" height="17" rx="8.5" '
            f'fill="{col}"><title>{escape(str(lab))}: {fmt_num(v)}</title></rect>'
            f'<text x="{width - 6}" y="{y + 18}" text-anchor="end" '
            f'class="tn-hbar-v">{fmt_num(v)}</text>'
        )
    return mark_safe(
        f'<svg class="tn-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}"><title>{escape(label)}</title>{rows}</svg>'
    )


def weather_ribbon(days, label, height=180):
    """8-day temperature ribbon; bars coloured by severity.

    days = [{'label', 'temp': float, 'severity', 'anomaly': str}, …]
    """
    width, left, right, top_pad, bottom = 560, 44, 12, 30, 30
    plot_w = width - left - right
    plot_h = height - top_pad - bottom
    temps = [float(d['temp']) for d in days] or [0.0]
    lo, hi = math.floor(min(temps)), math.ceil(max(temps))
    if hi - lo < 2:
        hi = lo + 2
    span = hi - lo
    n = max(len(days), 1)
    slot = plot_w / n
    bar_w = slot * 0.52
    base_y = top_pad + plot_h
    grid = ''
    for frac in (0, 0.5, 1):
        y = base_y - plot_h * frac
        grid += (
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-dasharray="2 5"/>'
            f'<text x="{left - 7}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="tn-axis">{lo + span * frac:.0f}°</text>'
        )
    bars = ''
    for i, d in enumerate(days):
        cx = left + slot * (i + 0.5)
        t = float(d['temp'])
        bh = max((t - lo) / span * plot_h, 3)
        y = base_y - bh
        col = SEVERITY_COLORS.get(d.get('severity', ''), ICE)
        title = (f"{d['label']} · {t:.1f}°C · {d.get('severity', '')} "
                 f"{d.get('anomaly', '')}")
        bars += (
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
            f'height="{bh:.1f}" rx="4" fill="{col}" opacity=".92">'
            f'<title>{escape(title)}</title></rect>'
            f'<text x="{cx:.1f}" y="{y - 6:.1f}" text-anchor="middle" '
            f'class="tn-val">{t:.0f}°</text>'
            f'<text x="{cx:.1f}" y="{height - 9}" text-anchor="middle" '
            f'class="tn-axis">{escape(str(d["label"]))}</text>'
        )
    return mark_safe(
        f'<svg class="tn-chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(label)}"><title>{escape(label)}</title>'
        f'{grid}{bars}</svg>'
    )
