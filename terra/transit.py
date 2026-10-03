"""Terra Nova transit — village timetables, fares and the welcome bonus.

Timetables are computed for "today" on every request so the departure board
always shows live, countable departures from the Novarian's village stop.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone

WELCOME_BONUS = Decimal('10000.000000')
CHILD_DISCOUNT = Decimal('0.5')          # children pay half fare
TICKET_WINDOW_MINUTES = 30               # QR valid until departure + 30 min

VILLAGES = {
    'aurelia': 'Habitat 12 · Aurelia Basin',
    'vermilion': 'Drift Station 4 · Vermilion Steps',
    'glasslands': 'Frostwall Hamlet · Glass Tundra',
    'pelagos': 'Tidepool Village · Pelagos Deep',
}


def _times(start_h, start_m, step_minutes, end_h, end_m):
    out = []
    minute = start_h * 60 + start_m
    end = end_h * 60 + end_m
    while minute <= end:
        out.append(f'{minute // 60:02d}:{minute % 60:02d}')
        minute += step_minutes
    return out


# One bus per sector (serves that village) + two inter-city trains.
ROUTES = [
    {'id': 'B1', 'kind': 'bus', 'name': 'Basin Loop Bus', 'sector': 'aurelia',
     'destination': 'Spaceport Terminal', 'fare': Decimal('0.025000'),
     'times': _times(5, 40, 20, 23, 20)},
    {'id': 'B2', 'kind': 'bus', 'name': 'Oxide Line Bus', 'sector': 'vermilion',
     'destination': 'Oxide Market Yard', 'fare': Decimal('0.025000'),
     'times': _times(5, 30, 25, 23, 5)},
    {'id': 'B3', 'kind': 'bus', 'name': 'Frostwall Shuttle', 'sector': 'glasslands',
     'destination': 'Observatory Siding', 'fare': Decimal('0.022000'),
     'times': _times(6, 0, 30, 22, 30)},
    {'id': 'B4', 'kind': 'bus', 'name': 'Tidepool Runner', 'sector': 'pelagos',
     'destination': 'Deep Harbor Pier', 'fare': Decimal('0.030000'),
     'times': _times(5, 50, 20, 22, 50)},
    {'id': 'T1', 'kind': 'train', 'name': 'Continental Express', 'sector': None,
     'destination': 'Cross-continental loop', 'fare': Decimal('0.060000'),
     'times': _times(5, 5, 60, 23, 5)},
    {'id': 'T2', 'kind': 'train', 'name': 'Pelagos Nightliner', 'sector': None,
     'destination': 'Deep Harbor via Aurelia', 'fare': Decimal('0.045000'),
     'times': _times(6, 40, 120, 22, 40)},
]

ROUTES_BY_ID = {route['id']: route for route in ROUTES}


def routes_for(sector):
    """Every route that stops at this village."""
    return [r for r in ROUTES if r['sector'] in (None, sector)]


def fare_for(route, traveler):
    """Adult fare, halved for children."""
    fare = route['fare']
    if traveler is not None and traveler.is_child:
        fare = fare * CHILD_DISCOUNT
    return fare.quantize(Decimal('0.000001'))


def _departure(day, hhmm):
    hour, minute = (int(part) for part in hhmm.split(':'))
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def timetable(sector, limit=10, now=None):
    """The next departures from this village, today plus tomorrow if needed."""
    now = now or timezone.localtime()
    today = now.date()
    rows = []
    for route in routes_for(sector):
        for hhmm in route['times']:
            departure = _departure(today, hhmm)
            if departure > now:
                rows.append((departure, route, False))
    rows.sort(key=lambda row: row[0])

    if len(rows) < limit:
        tomorrow = today + timedelta(days=1)
        extra = sorted(
            (_departure(tomorrow, hhmm), route, True)
            for route in routes_for(sector)
            for hhmm in route['times']
        )
        rows.extend(extra[:limit - len(rows)])

    board = []
    for departure, route, is_tomorrow in rows[:limit]:
        board.append({
            'route': route['id'],
            'kind': route['kind'],
            'name': route['name'],
            'destination': route['destination'],
            'fare': route['fare'],
            'time_label': departure.strftime('%H:%M'),
            'day_label': 'Tomorrow' if is_tomorrow else 'Today',
            'depart': departure,
            'epoch': int(departure.timestamp()),
            'value': f"{route['id']}|{int(departure.timestamp())}",
        })
    return board


def ticket_allowed_epochs(route):
    """All epochs today+tomorrow a paid departure may reference (validation)."""
    now = timezone.localtime()
    allowed = set()
    for day in (now.date(), now.date() + timedelta(days=1)):
        for hhmm in route['times']:
            allowed.add(int(_departure(day, hhmm).timestamp()))
    return allowed
