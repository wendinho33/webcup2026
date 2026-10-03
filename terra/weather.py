"""Terra Nova weather — deterministic conditions + a week-long heat simulation.

Everything derives from the current date/hour so the planet feels alive
without external APIs. The heat simulation covers today .. today+7 and every
day crosses the alert threshold, so Novarians receive at least a week of
temperature-rise notifications.
"""
import math
import random
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

# Seasonal means per surveyed sector (°C).
SECTORS = {
    'aurelia': {'name': 'Aurelia Basin', 'base': 29.0, 'humid': 74},
    'vermilion': {'name': 'Vermilion Steps', 'base': 36.0, 'humid': 22},
    'glasslands': {'name': 'The Glass Tundra', 'base': -12.0, 'humid': 48},
    'pelagos': {'name': 'Pelagos Deep', 'base': 24.0, 'humid': 86},
}

CONDITIONS = ['Clear', 'High haze', 'Dust drift', 'Overcast', 'Aurora night']
CONDITION_ICONS = {
    'Clear': 'sun',
    'High haze': 'haze',
    'Dust drift': 'dust',
    'Overcast': 'cloud',
    'Aurora night': 'aurora',
}

# Eight days (today .. +7): °C above the seasonal mean. Every entry crosses
# the alert threshold, which is what drives the week of notifications.
HEAT_ANOMALY = [Decimal('8.0'), Decimal('10.0'), Decimal('12.0'),
                Decimal('15.0'), Decimal('14.0'), Decimal('12.0'),
                Decimal('10.0'), Decimal('8.0')]
SIMULATION_DAYS = len(HEAT_ANOMALY)  # 8 days ≥ 1 week
ALERT_THRESHOLD = Decimal('7.0')

SEVERITIES = [
    (Decimal('14'), 'extreme'),
    (Decimal('10'), 'high'),
    (Decimal('0'), 'elevated'),
]


def severity_for(anomaly):
    for floor, name in SEVERITIES:
        if anomaly >= floor:
            return name
    return 'elevated'


def _rng(day, salt=''):
    """Deterministic generator for a given date (stable within the day)."""
    return random.Random(f'{day.isoformat()}|{salt}')


def hour_curve(now=None):
    """Diurnal temperature curve: coolest ~05:00, peak ~15:00."""
    now = now or timezone.localtime()
    return round(math.sin((now.hour - 9) * math.pi / 12), 2)


def sector_conditions(day=None, now=None):
    """Current conditions for every surveyed sector."""
    day = day or timezone.localdate()
    now = now or timezone.localtime()
    offset = (day - timezone.localdate()).days
    anomaly = HEAT_ANOMALY[min(max(offset, 0), SIMULATION_DAYS - 1)]
    curve = hour_curve(now)

    out = {}
    for key, meta in SECTORS.items():
        rng = _rng(day, key)
        temp = round(meta['base'] + float(anomaly) + curve * 4
                     + rng.uniform(-1.2, 1.2), 1)
        condition = rng.choice(CONDITIONS)
        out[key] = {
            'key': key,
            'name': meta['name'],
            'temp': temp,
            'feels': round(temp + (3.5 if meta['humid'] > 60 else 1.0), 1),
            'condition': condition,
            'icon': CONDITION_ICONS[condition],
            'humidity': meta['humid'] + rng.randint(-4, 4),
            'wind': rng.randint(6, 34),
            'anomaly': float(anomaly),
        }
    return out


def current_conditions(now=None):
    """Planet-wide headline conditions (mean of the four sectors)."""
    now = now or timezone.localtime()
    sectors = sector_conditions(now=now)
    temps = [s['temp'] for s in sectors.values()]
    mean = round(sum(temps) / len(temps), 1)
    rng = _rng(now.date(), 'global')
    condition = 'High haze' if mean > 30 else 'Clear'
    return {
        'temp': mean,
        'feels': round(mean + 2.4, 1),
        'condition': condition,
        'icon': CONDITION_ICONS[condition],
        'humidity': 58 + rng.randint(-5, 5),
        'wind': rng.randint(10, 28),
        'observed_at': now.strftime('%H:%M'),
        'mean_summer': 24.0,
    }
def forecast(days=SIMULATION_DAYS):
    """Daily outlook for the whole heat simulation window."""
    today = timezone.localdate()
    out = []
    for offset in range(days):
        day = today + timedelta(days=offset)
        anomaly = HEAT_ANOMALY[offset]
        rng = _rng(day, 'forecast')
        high = round(31 + float(anomaly), 1)
        low = round(high - rng.uniform(7, 10), 1)
        condition = rng.choice(CONDITIONS)
        out.append({
            'day': day,
            'offset': offset,
            'label': 'Today' if offset == 0 else day.strftime('%a %d'),
            'condition': condition,
            'icon': CONDITION_ICONS[condition],
            'high': high,
            'low': round(low, 1),
            'anomaly': anomaly,
            'severity': severity_for(anomaly),
        })
    return out


def build_alert(day, anomaly, fc_entry):
    """Compose the notification copy for one simulation day."""
    severity = severity_for(anomaly)
    peak_sector = 'Vermilion Steps' if severity != 'elevated' else 'Aurelia Basin'
    headlines = {
        'elevated': 'Heat advisory — temperatures climbing',
        'high': 'High heat alert — surface temperatures rising',
        'extreme': 'EXTREME HEAT — shelter during midday hours',
    }
    message = (
        f'{headlines[severity]} on Terra Nova. {peak_sector} reaching '
        f'{fc_entry["high"]}°C, +{anomaly}°C above the seasonal mean. '
        'Drink water, limit surface work 11:00–16:00, and keep to shaded '
        'routes between habitats.'
    )
    return severity, headlines[severity], message


def ensure_alerts():
    """Create the rolling 8-day heat simulation (idempotent).

    Returns the alerts that did not exist before this call.
    """
    from .models import WeatherAlert  # local import avoids circulars

    today = timezone.localdate()
    entries = forecast()
    created = []
    for offset, anomaly in enumerate(HEAT_ANOMALY):
        day = today + timedelta(days=offset)
        entry = entries[offset]
        severity, headline, message = build_alert(day, anomaly, entry)
        alert, was_created = WeatherAlert.objects.get_or_create(
            day=day,
            defaults={
                'severity': severity,
                'temp_c': Decimal(str(entry['high'])),
                'anomaly': anomaly,
                'headline': headline,
                'message': message,
                'kind': 'heat',
            },
        )
        if was_created:
            created.append(alert)
    return created


def today_alert():
    from .models import WeatherAlert
    return WeatherAlert.objects.filter(day=timezone.localdate()).first()


def simulate_alert():
    """A fresh, immediate alert payload for the demo trigger button.

    Does not touch the database — it mirrors the most severe day of the
    running simulation so a notification can be demonstrated on demand.
    """
    entries = forecast()
    peak = max(entries, key=lambda e: e['anomaly'])
    severity, headline, message = build_alert(
        peak['day'], peak['anomaly'], peak,
    )
    return {
        'id': f'sim-{peak["day"].isoformat()}',
        'severity': severity,
        'headline': headline,
        'message': message,
        'temp': peak['high'],
        'day': peak['day'].isoformat(),
        'is_simulation': True,
    }
