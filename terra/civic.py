"""Novarian civic services — taxation, records, waste, health & facilities.

Everything personal is derived deterministically from the account (no extra
storage for read-only facts), so the portal is stable between visits.
"""
import hashlib
import random
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

# --- taxation -------------------------------------------------------------
TAX_SCHEDULE = {
    'aurelia': Decimal('0.350000'),
    'vermilion': Decimal('0.420000'),
    'glasslands': Decimal('0.280000'),
    'pelagos': Decimal('0.510000'),
}
PRIORITY_SURCHARGE = Decimal('0.150000')

# --- pension --------------------------------------------------------------
PENSION_AGE = 65
PENSION_MONTHLY = Decimal('0.600000')

# --- Terra Watch ----------------------------------------------------------
TERRA_WATCH_PRICE = Decimal('50.000000')

# --- waste management -----------------------------------------------------
WASTE_DAYS = {          # weekday numbers: 0=Mon … 6=Sun
    'aurelia': (1, 4),   # Tue & Fri
    'vermilion': (2, 5),  # Wed & Sat
    'glasslands': (0, 3),  # Mon & Thu
    'pelagos': (1, 5),   # Tue & Sat
}
WASTE_NOTES = {
    'aurelia': 'General waste twice weekly · organics every Tuesday.',
    'vermilion': 'Dust-sealed collection · glass & metal every Wednesday.',
    'glasslands': 'Frozen-load compactor · recyclables every Thursday.',
    'pelagos': 'Salvage skiff collection · hazardables by request.',
}
WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# --- health facilities ----------------------------------------------------
FACILITIES = [
    {'id': 'nova-central', 'name': 'Nova Central Hospital',
     'sector': 'aurelia', 'kind': 'Hospital', 'hours': '24 h',
     'services': 'Trauma · Maternity · Surgery'},
    {'id': 'lagoon-clinic', 'name': 'Lagoon Field Clinic',
     'sector': 'aurelia', 'kind': 'Clinic', 'hours': '07:00–22:00',
     'services': 'General care · Vaccination'},
    {'id': 'vermilion-dust', 'name': 'Vermilion Dust Clinic',
     'sector': 'vermilion', 'kind': 'Clinic', 'hours': '08:00–20:00',
     'services': 'Respiratory · Heat stress'},
    {'id': 'glass-medpost', 'name': 'Glasslands Medpost',
     'sector': 'glasslands', 'kind': 'Medpost', 'hours': '24 h',
     'services': 'Frostbite · Oxygen bar'},
    {'id': 'pelagos-hyper', 'name': 'Pelagos Hyperbaric Centre',
     'sector': 'pelagos', 'kind': 'Hospital', 'hours': '24 h',
     'services': 'Diving medicine · Hyperbaric'},
]


def _seed(*parts):
    return random.Random('|'.join(str(p) for p in parts))


def ssn(user):
    """Novarian social security number — stable per account."""
    digest = hashlib.sha1(f'{user.id}:novaria-ssn'.encode()).hexdigest()
    return f'SSN-TN-{int(digest[:8], 16) % 1000000:06d}'


def device_id(user):
    """Terra Watch hardware identifier."""
    return 'TW-' + hashlib.sha1(f'watch:{user.id}'.encode()).hexdigest()[:6].upper()


def fiscal_code(today=None):
    today = today or timezone.localdate()
    quarter = (today.month - 1) // 3 + 1
    return f'FY{today.year}-Q{quarter}'


def tax_amount(profile):
    """Sector levy + priority-boarding surcharge, in TRX."""
    amount = TAX_SCHEDULE.get(profile.sector, TAX_SCHEDULE['aurelia'])
    if profile.priority:
        amount += PRIORITY_SURCHARGE
    return amount


def age_on(dob, today=None):
    if not dob:
        return None
    today = today or timezone.localdate()
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def pension_state(profile):
    """(age, eligible, months_until) for the pension desk."""
    age = age_on(profile.date_of_birth)
    if age is None:
        return None, False, None
    eligible = age >= PENSION_AGE
    if eligible:
        return age, True, 0
    months = (PENSION_AGE - age) * 12
    return age, False, months
def social_security(user):
    """Read-only social security record, derived from the account."""
    rng = _seed('sss', user.id)
    today = timezone.localdate()
    contributions = []
    total = Decimal('0')
    for back in range(6, 0, -1):
        month = today.month - back
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        amount = Decimal(str(round(rng.uniform(0.04, 0.11), 4)))
        total += amount
        contributions.append({
            'period': date(year, month, 1).strftime('%b %Y'),
            'amount': amount,
        })
    return {
        'number': ssn(user),
        'standing': 'Active · in good standing',
        'contributions': contributions,
        'total': total.quantize(Decimal('0.0001')),
        'coverages': [
            ('Health care', 'Full cover · Terra Watch streaming'),
            ('Injury & disability', 'Active'),
            ('Elder pension', f'Eligible from age {PENSION_AGE}'),
            ('Transit & waste', 'Covered by sector levy'),
            ('Dependants', 'Up to 4 registered'),
        ],
    }


def waste_schedule(sector, today=None):
    """Next collection day(s) for a sector."""
    today = today or timezone.localdate()
    days = WASTE_DAYS.get(sector, WASTE_DAYS['aurelia'])
    options = []
    for weekday in days:
        delta = (weekday - today.weekday()) % 7
        options.append(today + timedelta(days=delta))
    nxt = min(options)
    return {
        'days': ', '.join(WEEKDAY_NAMES[d] for d in days),
        'next': nxt,
        'in_days': (nxt - today).days,
        'note': WASTE_NOTES.get(sector, WASTE_NOTES['aurelia']),
    }


def facilities_for(user):
    """Facilities sorted nearest-first; your sector is always walkable."""
    sector = None
    if user is not None and user.is_authenticated:
        from .models import Profile
        sector = Profile.objects.filter(user=user).values_list(
            'sector', flat=True,
        ).first()

    rows = []
    for facility in FACILITIES:
        rng = _seed('dist', user.id if user else 0, facility['id'])
        if sector and facility['sector'] == sector:
            distance = round(rng.uniform(0.8, 4.5), 1)
        else:
            distance = round(rng.uniform(6.0, 15.0), 1)
        rows.append({
            **facility,
            'distance': distance,
            'walk_min': max(4, int(distance * 12)),
            'is_home': bool(sector and facility['sector'] == sector),
        })
    rows.sort(key=lambda row: row['distance'])
    return rows


def vitals(user, today=None):
    """Daily Terra Watch reading set (deterministic per day)."""
    today = today or timezone.localdate()
    rng = _seed('vitals', user.id, today.isoformat())

    from .weather import current_conditions
    anomaly = round(
        current_conditions()['temp'] - current_conditions()['mean_summer'], 1,
    )
    heat_strain = anomaly >= 8

    bars = []
    bar_rng = _seed('ready', user.id, today.isoformat())
    for offset in range(7):
        bars.append(int(bar_rng.uniform(58, 96)))

    return {
        'device': device_id(user),
        'heart_rate': rng.randint(58, 76),
        'spo2': rng.randint(96, 99),
        'sleep': round(rng.uniform(6.1, 8.4), 1),
        'steps': rng.randint(6400, 12800),
        'stress': rng.randint(12, 38),
        'readiness': bars[-1],
        'bars': bars,
        'heat_strain': heat_strain,
        'anomaly': anomaly,
    }


def get_or_create_tax_bill(profile):
    """The current fiscal bill for this Novarian (idempotent)."""
    from .models import TaxBill
    return TaxBill.objects.get_or_create(
        user=profile.user,
        code=fiscal_code(),
        defaults={'amount_trx': tax_amount(profile)},
    )


def months_since_claim(user):
    """True when this month's pension has already been claimed."""
    from .models import Transaction
    today = timezone.localdate()
    month_start = today.replace(day=1)
    return Transaction.objects.filter(
        user=user, kind='pension', created_at__date__gte=month_start,
    ).exists()