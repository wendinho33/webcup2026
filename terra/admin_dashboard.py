"""Live data assembly for the Terra Nova admin control deck.

Every figure is a precise database aggregate computed at page load (the
deck is deliberately uncached so operators always read the current ledger);
every visual is a Terra Nova SVG chart primitive from ``terra.charts``.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import Abs, TruncDate
from django.urls import reverse
from django.utils import timezone

from . import charts
from .models import (
    ChatThread,
    CivicRequest,
    FareTicket,
    Profile,
    Transaction,
    WeatherAlert,
)

User = get_user_model()

SECTOR_LABELS = {
    'aurelia': 'Aurelia Basin',
    'vermilion': 'Vermilion Steps',
    'glasslands': 'The Glass Tundra',
    'pelagos': 'Pelagos Deep',
}
SECTOR_COLORS = {
    'aurelia': charts.SOLAR,
    'vermilion': charts.SOLAR2,
    'glasslands': charts.ICE,
    'pelagos': charts.MINT,
}
CIVIC_STAGES = [
    ('received', 'Received', charts.ICE),
    ('review', 'Under review', charts.SOLAR),
    ('approved', 'Approved', charts.MINT),
    ('scheduled', 'Scheduled', charts.DIM),
]
CHAT_STATUS_COLORS = {
    'open': charts.ICE,
    'ai_handling': charts.SOLAR,
    'escalated': charts.SOLAR2,
    'resolved': charts.MINT,
}


def _daily_counts(qs, date_field, days=14):
    """[(date, count)] for the last ``days`` local days — zero-filled."""
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    rows = (
        qs.filter(**{f'{date_field}__date__gte': start})
        .annotate(day=TruncDate(date_field))
        .values('day')
        .annotate(n=Count('id'))
    )
    mapping = {r['day']: r['n'] for r in rows}
    return [
        (start + timedelta(days=i), mapping.get(start + timedelta(days=i), 0))
        for i in range(days)
    ]


def _delta(qs, date_field):
    """(this 7 days, previous 7 days, difference) — exact counts."""
    now = timezone.now()
    week = timedelta(days=7)
    this = qs.filter(**{f'{date_field}__gte': now - week}).count()
    prev = qs.filter(**{
        f'{date_field}__gte': now - 2 * week,
        f'{date_field}__lt': now - week,
    }).count()
    return this, prev, this - prev


def money(value, decimals=2):
    if value is None:
        value = 0
    return f'{value:,.{decimals}f}'


def pct(part, whole):
    return f'{100 * part / whole:.0f}%' if whole else '—'


def build_kpis():
    """Eight headline figures, each with exact value + trend + deep link."""
    users = User.objects.all()
    profiles = Profile.objects.all()

    signup_series = [n for _, n in _daily_counts(users, 'date_joined', 14)]
    s_this, _s_prev, s_delta = _delta(users, 'date_joined')
    wallet = profiles.aggregate(trx=Sum('trx_balance'), usd=Sum('usd_balance'))
    trx_total = wallet['trx'] or Decimal('0')
    usd_total = wallet['usd'] or Decimal('0')
    profile_total = profiles.count()

    flow_qs = Transaction.objects.all()
    flow14 = flow_qs.filter(created_at__gte=timezone.now() - timedelta(days=14))
    flow_series = [n for _, n in _daily_counts(flow_qs, 'created_at', 14)]
    vol14 = flow14.aggregate(v=Sum(Abs('trx')))['v'] or Decimal('0')

    civic_total = CivicRequest.objects.count()
    triage = 0
    for req in CivicRequest.objects.order_by('-created_at')[:500]:
        if req.status_slug in ('received', 'review'):
            triage += 1

    threads_total = ChatThread.objects.count()
    unresolved = ChatThread.objects.exclude(status='resolved').count()

    watch = profiles.filter(terra_watch=True).count()
    tickets_total = FareTicket.objects.count()
    tickets_used = FareTicket.objects.filter(used=True).count()

    return [
        {
            'label': 'NOVARIANS',
            'value': f'{users.count():,}',
            'note': f'+{s_this} this week ({s_delta:+d} vs prior 7d)',
            'trend': charts.sparkline(signup_series, charts.ICE, label='crew admissions'),
            'href': reverse('admin:auth_user_changelist'),
            'tone': 'ice',
        },
        {
            'label': 'TRX IN CIRCULATION',
            'value': money(trx_total),
            'note': f'TerraX held by {profile_total:,} wallets',
            'trend': '',
            'href': reverse('admin:terra_profile_changelist'),
            'tone': 'mint',
        },
        {
            'label': 'EARTH CREDITS',
            'value': money(usd_total),
            'note': 'fiat-equivalent reserves (USD)',
            'trend': '',
            'href': reverse('admin:terra_profile_changelist'),
            'tone': 'plain',
        },
        {
            'label': 'TERRAX FLOW · 14D',
            'value': f'{flow14.count():,}',
            'note': f'{money(vol14)} TRX moved',
            'trend': charts.sparkline(flow_series, charts.SOLAR, label='settled trades, 14 days'),
            'href': reverse('admin:terra_transaction_changelist'),
            'tone': 'solar',
        },
        {
            'label': 'TRIAGE QUEUE',
            'value': f'{triage:,}',
            'note': f'{civic_total:,} civic signals filed',
            'trend': '',
            'href': reverse('admin:terra_civicrequest_changelist'),
            'tone': 'solar2',
        },
        {
            'label': 'OPEN CHAT',
            'value': f'{unresolved:,}',
            'note': f'{threads_total:,} threads in Terra Chat',
            'trend': '',
            'href': reverse('admin:terra_chatthread_changelist'),
            'tone': 'solar',
        },
        {
            'label': 'TERRA WATCH PAIRS',
            'value': f'{watch:,}',
            'note': f'{pct(watch, profile_total)} of {profile_total:,} wallets',
            'trend': '',
            'href': reverse('admin:terra_profile_changelist'),
            'tone': 'mint',
        },
        {
            'label': 'SCANNED PASSES',
            'value': f'{tickets_used:,}',
            'note': f'{pct(tickets_used, tickets_total)} of {tickets_total:,} issued',
            'trend': '',
            'href': reverse('admin:terra_fareticket_changelist'),
            'tone': 'ice',
        },
    ]


def build_charts():
    """Seven chart payloads: {svg, note, legend?} for the deck template."""
    # ── 1. Crew admissions, 14-day area ────────────────────────────────
    pairs = _daily_counts(User.objects.all(), 'date_joined', 14)
    labels = [d.strftime('%m-%d') for d, _ in pairs]
    values = [n for _, n in pairs]
    s_this, _s_prev, s_delta = _delta(User.objects.all(), 'date_joined')
    signups = {
        'svg': charts.area_chart(
            labels, values, 'Crew admissions per day, last 14 days',
            color=charts.ICE, gid='tn-signups',
        ),
        'note': (f'{sum(values)} admissions in 14 days · +{s_this} this week '
                 f'({s_delta:+d} vs prior week)'),
    }

    # ── 2. TerraX settlements per day, bars ────────────────────────────
    pairs = _daily_counts(Transaction.objects.all(), 'created_at', 14)
    labels = [d.strftime('%m-%d') for d, _ in pairs]
    values = [n for _, n in pairs]
    now = timezone.now()
    flow14 = Transaction.objects.filter(
        created_at__gte=now - timedelta(days=14),
    )
    vol = flow14.aggregate(v=Sum(Abs('trx')))['v'] or Decimal('0')
    credits = flow14.aggregate(v=Sum(Abs('usd')))['v'] or Decimal('0')
    flow = {
        'svg': charts.bar_chart(
            list(zip(labels, values)), 'TerraX settlements per day, 14 days',
            color=charts.MINT,
        ),
        'note': (f'{flow14.count():,} settlements · {money(vol)} TRX · '
                 f'{money(credits)} credits moved'),
    }

    # ── 3. Wallets by sector, donut ────────────────────────────────────
    rows = Profile.objects.values('sector').annotate(n=Count('id'))
    counts = {r['sector']: r['n'] for r in rows}
    segments = [
        (SECTOR_LABELS[sec], counts.get(sec, 0), SECTOR_COLORS[sec])
        for sec in SECTOR_LABELS
    ]
    total_profiles = sum(counts.values())
    sectors = {
        'svg': charts.donut(segments, f'{total_profiles:,}', 'WALLETS'),
        'legend': [
            {'label': lbl, 'value': n, 'color': col} for lbl, n, col in segments
        ],
        'note': 'surveyed biome distribution of registered wallets',
    }

    # ── 4. Civic pipeline by live (age-driven) stage ───────────────────
    stage_counts = {slug: 0 for slug, _label, _col in CIVIC_STAGES}
    civic_qs = CivicRequest.objects.all()
    for req in civic_qs[:500]:
        if req.status_slug in stage_counts:
            stage_counts[req.status_slug] += 1
    civic_items = [
        (label, stage_counts[slug], col) for slug, label, col in CIVIC_STAGES
    ]
    civic = {
        'svg': charts.hbars(civic_items, 'Civic request pipeline by stage'),
        'note': (f'{civic_qs.count():,} signals · stages derived from age '
                 f'in real time (road / waste / medical ladders)'),
        'stages': [
            {'label': label, 'n': stage_counts[slug]}
            for slug, label, _col in CIVIC_STAGES
        ],
    }

    # ── 5. Terra Chat thread states, donut ─────────────────────────────
    rows = ChatThread.objects.values('status').annotate(n=Count('id'))
    counts = {r['status']: r['n'] for r in rows}
    labels_map = dict(ChatThread.STATUS_CHOICES)
    segments = [
        (labels_map[slug], counts.get(slug, 0), CHAT_STATUS_COLORS[slug])
        for slug, _label in ChatThread.STATUS_CHOICES
    ]
    unresolved = sum(v for k, v in counts.items() if k != 'resolved')
    chat = {
        'svg': charts.donut(segments, f'{unresolved:,}', 'UNRESOLVED'),
        'legend': [
            {'label': lbl, 'value': n, 'color': col} for lbl, n, col in segments
        ],
        'note': f'{sum(counts.values()):,} threads across Terra AI and agents',
    }

    # ── 6. Fare ticket states ──────────────────────────────────────────
    tickets_total = FareTicket.objects.count()
    used = FareTicket.objects.filter(used=True).count()
    expired = FareTicket.objects.filter(
        used=False, departure__lt=timezone.now() - timedelta(minutes=30),
    ).count()
    valid = tickets_total - used - expired
    tickets = {
        'svg': charts.hbars(
            [('Valid', valid, charts.MINT), ('Boarded', used, charts.SOLAR),
             ('Departed', expired, charts.DIM)],
            'Fare ticket states',
        ),
        'note': (f'{used:,}/{tickets_total:,} scanned · {pct(used, tickets_total)} '
                 f'boarding rate'),
    }

    # ── 7. Heat ribbon, next 8 days ────────────────────────────────────
    today = timezone.localdate()
    alerts = list(WeatherAlert.objects.filter(day__gte=today).order_by('day')[:8])
    if alerts:
        ribbon_days = [
            {
                'label': a.day.strftime('%a %d'),
                'temp': float(a.temp_c),
                'severity': a.severity,
                'anomaly': f'{a.anomaly:+}°C',
            }
            for a in alerts
        ]
        weather = {
            'svg': charts.weather_ribbon(
                ribbon_days, 'Heat simulation, next 8 days',
            ),
            'note': (f'{alerts[0].day.strftime("%d %b")} → '
                     f'{alerts[-1].day.strftime("%d %b")} · coloured by severity'),
            'legend': [
                {'label': 'Elevated', 'color': charts.ICE},
                {'label': 'High', 'color': charts.SOLAR},
                {'label': 'Extreme', 'color': charts.SOLAR2},
            ],
        }
    else:
        weather = {
            'svg': '',
            'note': 'No forecast rows — open Weather once to seed the simulation.',
            'legend': [],
        }

    return {
        'chart_signups': signups,
        'chart_flow': flow,
        'chart_sectors': sectors,
        'chart_civic': civic,
        'chart_chat': chat,
        'chart_tickets': tickets,
        'chart_weather': weather,
    }


def build_signals(limit=10):
    """Merged, newest-first activity feed across the core registries."""
    items = []

    def add(ts, kind, label, url):
        items.append({'ts': ts, 'kind': kind, 'label': label, 'url': url})

    for u in User.objects.order_by('-date_joined')[:3]:
        add(u.date_joined, 'CREW', f'{u.username} joined',
            reverse('admin:auth_user_change', args=[u.pk]))
    for t in Transaction.objects.select_related('user').order_by('-created_at')[:3]:
        add(t.created_at, 'TERRAX',
            f'{t.get_kind_display()} {t.trx:+.4g} TRX · {t.user.username}',
            reverse('admin:terra_transaction_change', args=[t.pk]))
    for c in CivicRequest.objects.order_by('-created_at')[:3]:
        add(c.created_at, 'CIVIC',
            f'{c.tracking} · {c.status_label} · {c.location[:34]}',
            reverse('admin:terra_civicrequest_change', args=[c.pk]))
    for th in ChatThread.objects.order_by('-updated_at')[:3]:
        add(th.updated_at, 'CHAT', f'{th.tracking} · {th.subject[:34]}',
            reverse('admin:terra_chatthread_change', args=[th.pk]))
    for w in WeatherAlert.objects.order_by('-created_at')[:2]:
        add(w.created_at, 'WX',
            f'{w.day} · {w.get_severity_display()} · {w.temp_c}°C',
            reverse('admin:terra_weatheralert_change', args=[w.pk]))

    items.sort(key=lambda i: i['ts'], reverse=True)
    return items[:limit]


def dashboard_context():
    """Everything the control-deck template needs, computed once."""
    ctx = build_charts()
    ctx.update({
        'kpis': build_kpis(),
        'signals': build_signals(),
        'stamp': timezone.localtime().strftime('%d %b %Y · %H:%M %Z'),
    })
    return ctx
