"""The passenger dossier — every record Terra Nova holds, as one PDF.

Built with the dependency-free ``terra.pdfgen`` writer: branded cover band,
section bars, key/value blocks and zebra tables, paginated automatically.
"""
from decimal import Decimal

from django.utils import timezone

from .pdfgen import CONTENT_W, Document

TRX = Decimal('1')


def _money(value):
    return f'{value:,.2f} USD'


def _trx(value):
    return f'{value:,.6f} TRX'


def _dt(value):
    return value.strftime('%d %b %Y, %H:%M') if value else '—'


def _d(value):
    return value.strftime('%d %b %Y') if value else '—'


def build_dossier(user):
    """Render every record tied to ``user`` and return PDF bytes."""
    profile = getattr(user, 'profile', None)
    doc = Document(
        title=f'Passenger dossier — {user.username}',
        subject='Everything Terra Nova holds on this account',
        author='Terra Nova · Mission Control',
    )
    doc.footer = (
        f'Terra Nova · Passenger dossier · {user.username}'
        + (f' · {profile.callsign}' if profile else '')
        + f' · generated {timezone.now().strftime("%d %b %Y, %H:%M UTC")}'
    )

    _cover(doc, user, profile)
    _identity(doc, user, profile)
    _wallet(doc, profile, user)
    _transactions(doc, user)
    _civic(doc, user)
    _travel(doc, user)
    _chat(doc, user)
    _ratings(doc, user)
    _security(doc, user)
    _closing(doc)
    return doc.render()

def _cover(doc, user, profile):
    """Full-width branded cover band on page 1."""
    c = doc.page
    from .pdfgen import MARGIN_X, PAGE_W

    band_h = 150
    c.y -= band_h
    top = c.y + band_h
    c.rect(0, c.y, PAGE_W, band_h, (0.027, 0.043, 0.082))
    c.rect(0, c.y, PAGE_W, 3.5, (1.0, 0.698, 0.341))
    c.text(MARGIN_X, top - 52, 'TERRA NOVA', size=13,
           rgb=(1.0, 0.698, 0.341), bold=True)
    c.text(MARGIN_X, top - 84, 'Passenger dossier', size=26,
           rgb=(0.95, 0.97, 1.0), bold=True)
    c.text(MARGIN_X, top - 106,
           'Everything the colony holds on this account — one document.',
           size=10, rgb=(0.62, 0.7, 0.83))
    callsign = profile.callsign if profile else '—'
    c.text_right(PAGE_W - MARGIN_X, top - 52, f'CALLSIGN  {callsign}',
                 size=10, rgb=(0.62, 0.84, 0.7), bold=True)
    c.text_right(PAGE_W - MARGIN_X, top - 70,
                 f'GENERATED  {timezone.now().strftime("%d %b %Y, %H:%M UTC")}',
                 size=8.5, rgb=(0.55, 0.63, 0.76))
    c.text_right(PAGE_W - MARGIN_X, top - 86,
                 f'PASSENGER  {user.username}', size=8.5,
                 rgb=(0.55, 0.63, 0.76))
    c.y -= 26


def _identity(doc, user, profile):
    doc.heading('Identity record', note='ACCOUNT')
    rows = [
        ('Full name', user.get_full_name() or '—'),
        ('Passenger name', user.username),
        ('Email', user.email or '—'),
        ('Callsign', profile.callsign if profile else '—'),
        ('Sector', profile.sector_name if profile else '—'),
        ('Date of birth', _d(profile.date_of_birth) if profile else '—'),
        ('Log entry', (profile.tagline or '—') if profile else '—'),
        ('Member since', _dt(timezone.localtime(user.date_joined))),
        ('Account status', 'Active' if user.is_active else 'Suspended'),
        ('Staff', 'Yes' if user.is_staff else 'No'),
    ]
    doc.kv_rows(rows)


def _wallet(doc, profile, user):
    doc.heading('Wallet & clearance', note='TERRAX')
    if profile is None:
        doc.paragraph('No passenger record is attached to this account yet.')
        return
    rows = [
        ('TerraX balance', _trx(profile.trx_balance)),
        ('Earth credits', _money(profile.usd_balance)),
        ('Priority boarding', 'Yes' if profile.priority else 'No'),
        ('Terra Watch', 'Paired' if profile.terra_watch else 'Not paired'),
        ('Agent status', 'Novarian agent' if profile.is_agent else 'Passenger'),
        ('Profile picture', 'On file' if profile.avatar else 'None'),
    ]
    doc.kv_rows(rows)


def _transactions(doc, user):
    txns = list(user.transactions.all()[:80])
    doc.heading('TerraX ledger', note=f'{user.transactions.count()} ENTRIES')
    if not txns:
        doc.paragraph('No settled trades or service purchases on record.')
        return
    doc.table(
        ['Date', 'Kind', 'TRX', 'Credits (USD)', 'Note'],
        [[
            _dt(t.created_at), t.get_kind_display(), f'{t.trx:+.6f}',
            f'{t.usd:+,.2f}', t.note or '—',
        ] for t in txns],
        [88, 60, 84, 90, CONTENT_W - 322],
        aligns=['l', 'l', 'r', 'r', 'l'],
    )


def _civic(doc, user):
    requests = list(user.civic_requests.all()[:40])
    doc.heading('Civic requests', note='GOVERNMENT PORTAL')
    if not requests:
        doc.paragraph('No road, waste or medical requests on record.')
    else:
        doc.table(
            ['Tracking', 'Category', 'Stage', 'Location', 'Filed'],
            [[
                r.tracking, r.get_category_display(), r.status_label,
                r.location, _dt(r.created_at),
            ] for r in requests],
            [68, 84, 80, 157, CONTENT_W - 389],
        )
    bills = list(user.tax_bills.all()[:20])
    if bills:
        doc.heading('Tax bills', note='FISCAL RECORD')
        doc.table(
            ['Code', 'Amount (TRX)', 'Status', 'Paid'],
            [[
                b.code, f'{b.amount_trx:,.2f}', b.get_status_display(),
                _dt(b.paid_at),
            ] for b in bills],
            [110, 110, 90, CONTENT_W - 310],
            aligns=['l', 'r', 'l', 'l'],
        )


def _travel(doc, user):
    travelers = list(user.travelers.all())
    tickets = list(user.tickets.all()[:30])
    if not travelers and not tickets:
        return
    doc.heading('Travel manifest', note='TRANSPORT')
    if travelers:
        doc.table(
            ['Traveler', 'Relation', 'Fares'],
            [[
                t.name, t.get_relation_display(), str(t.tickets.count()),
            ] for t in travelers],
            [200, 120, CONTENT_W - 320],
        )
    if tickets:
        doc.table(
            ['Code', 'Route', 'Kind', 'Destination', 'Departs', 'Status'],
            [[
                t.code, t.route_name, t.get_kind_display() if hasattr(
                    t, 'get_kind_display') else t.kind,
                t.destination, _dt(t.departure), t.status_label,
            ] for t in tickets],
            [86, 96, 46, 96, 84, CONTENT_W - 408],
        )


def _chat(doc, user):
    threads = list(user.chat_threads.all()[:40])
    doc.heading('Terra Chat signals', note=f'{user.chat_threads.count()} THREADS')
    if not threads:
        doc.paragraph('No conversations with Terra AI or Novarian agents.')
        return
    doc.table(
        ['Signal', 'Subject', 'Kind', 'Status', 'Agent', 'Opened'],
        [[
            t.tracking, t.subject, t.get_kind_display(),
            t.get_status_display(),
            t.assigned_agent.username if t.assigned_agent_id else '—',
            _dt(t.created_at),
        ] for t in threads],
        [52, 148, 60, 104, 76, CONTENT_W - 440],
    )


def _ratings(doc, user):
    given = list(user.agent_ratings_given.select_related('agent')[:20])
    received = list(user.agent_ratings_received.select_related('user')[:20])
    if not given and not received:
        return
    doc.heading('Agent ratings', note='ACCOUNT CENTRE')
    if given:
        doc.paragraph('Ratings this passenger gave to Novarian agents:',
                      size=9, gap=4)
        doc.table(
            ['Agent', 'Stars', 'Comment', 'Updated'],
            [[
                r.agent.username, f'{r.rating}/5', r.comment or '—',
                _dt(r.updated_at),
            ] for r in given],
            [110, 56, CONTENT_W - 320, 100],
        )
    if received:
        doc.paragraph('Ratings received as a Novarian agent:', size=9, gap=4)
        doc.table(
            ['From', 'Stars', 'Comment', 'Updated'],
            [[
                r.user.username, f'{r.rating}/5', r.comment or '—',
                _dt(r.updated_at),
            ] for r in received],
            [110, 56, CONTENT_W - 320, 100],
        )


def _security(doc, user):
    devices = list(user.devices.all()[:20])
    attempts = list(user.login_attempts.all()[:20])
    notes = list(user.notifications.all()[:20])
    doc.heading('Security watch', note='DEVICES & ALERTS')
    if devices:
        doc.paragraph('Registered devices:', size=9, gap=4)
        doc.table(
            ['Fingerprint', 'Address', 'User agent', 'Last seen'],
            [[
                d.fingerprint[:16], d.ip_address or '—',
                d.user_agent or '—', _dt(d.last_seen),
            ] for d in devices],
            [104, 92, 168, CONTENT_W - 364],
        )
    if attempts:
        doc.paragraph('Rejected sign-in attempts:', size=9, gap=4)
        doc.table(
            ['Address', 'Targeted username', 'When'],
            [[a.ip_address or '—', a.username, _dt(a.created_at)]
             for a in attempts],
            [120, 190, CONTENT_W - 310],
        )
    if notes:
        doc.paragraph('Notification centre entries:', size=9, gap=4)
        doc.table(
            ['Kind', 'Title', 'Read', 'When'],
            [[
                n.get_kind_display(), n.title,
                'Yes' if n.is_read else 'No', _dt(n.created_at),
            ] for n in notes],
            [72, CONTENT_W - 320, 52, 96],
        )
    if not devices and not attempts and not notes:
        doc.paragraph('No security events on record.')


def _closing(doc):
    doc.heading('Statement')
    doc.paragraph(
        'This dossier was generated by Terra Nova Mission Control and '
        'reflects every record stored against the account at the moment of '
        'export: identity, wallet, ledger, civic activity, travel manifest, '
        'conversations, ratings and security events. Paperwork, signed.',
        size=9.5,
    )
    doc.paragraph(
        'Terra Nova · A second Earth · Expedition 01',
        size=8.5, rgb=(0.5, 0.55, 0.63), gap=2,
    )


