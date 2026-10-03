"""TerraX (TRX) market data.

TerraX is the currency of Terra Nova. Site rules:
    1 TRX = 1.25 x Bitcoin (USD)   — the headline market price
    1 TRX = 5 x Ethereum           — the site's declared Earth peg
Earth prices come from CoinGecko with a 60s cache and a safe fallback
so the market page never breaks when the network is unavailable.
"""
import json
import random
import urllib.request
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from django.core.cache import cache

COINGECKO_URL = (
    'https://api.coingecko.com/api/v3/simple/price'
    '?ids={ids}&vs_currencies=usd'
    '&include_24hr_change=true&include_market_cap=true'
)
CACHE_KEY = 'terra:earth-prices'
CACHE_TTL = 60

# Earth coins tracked on the market page (CoinGecko ids).
EARTH_COINS = [
    {'id': 'bitcoin', 'symbol': 'BTC', 'name': 'Bitcoin', 'glyph': '₿', 'cls': 'btc'},
    {'id': 'ethereum', 'symbol': 'ETH', 'name': 'Ethereum', 'glyph': 'Ξ', 'cls': 'eth'},
    {'id': 'solana', 'symbol': 'SOL', 'name': 'Solana', 'glyph': '◎', 'cls': 'sol'},
    {'id': 'binancecoin', 'symbol': 'BNB', 'name': 'BNB', 'glyph': '⬡', 'cls': 'bnb'},
    {'id': 'ripple', 'symbol': 'XRP', 'name': 'XRP', 'glyph': 'X', 'cls': 'xrp'},
    {'id': 'dogecoin', 'symbol': 'DOGE', 'name': 'Dogecoin', 'glyph': 'Ð', 'cls': 'doge'},
    {'id': 'cardano', 'symbol': 'ADA', 'name': 'Cardano', 'glyph': '₳', 'cls': 'ada'},
    {'id': 'litecoin', 'symbol': 'LTC', 'name': 'Litecoin', 'glyph': 'Ł', 'cls': 'ltc'},
]

BTC_PEG = Decimal('1.25')        # 1 TRX = 1.25 BTC
ETH_PEG = Decimal('5')           # 1 TRX = 5 ETH
BETA = Decimal('1.25')           # TRX daily move = 1.25 x BTC's move
EXCHANGE_FEE = Decimal('0.005')  # 0.5% on every trade
TRX_QUANTUM = Decimal('0.000001')
USD_QUANTUM = Decimal('0.01')

# Offline safety net: every tracked coin, keyed by CoinGecko id.
FALLBACK = {
    'bitcoin': {
        'price': Decimal('108450.00'),
        'change': Decimal('1.84'),
        'mcap': Decimal('2150000000000'),
    },
    'ethereum': {
        'price': Decimal('4182.50'),
        'change': Decimal('-0.72'),
        'mcap': Decimal('504000000000'),
    },
    'solana': {
        'price': Decimal('186.40'),
        'change': Decimal('2.31'),
        'mcap': Decimal('102000000000'),
    },
    'binancecoin': {
        'price': Decimal('712.30'),
        'change': Decimal('0.94'),
        'mcap': Decimal('103000000000'),
    },
    'ripple': {
        'price': Decimal('2.48'),
        'change': Decimal('-1.15'),
        'mcap': Decimal('144000000000'),
    },
    'dogecoin': {
        'price': Decimal('0.1842'),
        'change': Decimal('3.62'),
        'mcap': Decimal('27900000000'),
    },
    'cardano': {
        'price': Decimal('0.6120'),
        'change': Decimal('-0.48'),
        'mcap': Decimal('21800000000'),
    },
    'litecoin': {
        'price': Decimal('98.25'),
        'change': Decimal('1.07'),
        'mcap': Decimal('7420000000'),
    },
}

SERVICES = [
    {
        'slug': 'sector',
        'name': 'Sector transfer',
        'price': Decimal('0.400000'),
        'blurb': 'Leave the draw behind — pick any of the four surveyed '
                 'biomes and move your settlement there.',
        'input': 'sector',
    },
    {
        'slug': 'callsign',
        'name': 'Callsign rename',
        'price': Decimal('0.250000'),
        'blurb': 'Trade your issued callsign for one of your own. '
                 '3–24 characters: letters, digits and dashes.',
        'input': 'callsign',
    },
    {
        'slug': 'priority',
        'name': 'Priority boarding',
        'price': Decimal('2.000000'),
        'blurb': 'Flag your manifest entry with the priority marker '
                 'for Expedition 01.',
        'input': None,
    },
]


def get_service(slug):
    for service in SERVICES:
        if service['slug'] == slug:
            return service
    return None


def _finalize(prices, source):
    """Assemble the quote dict, keeping the legacy btc/eth keys."""
    earth = {'source': source, 'prices': prices}
    earth['btc'] = prices['bitcoin']['price']
    earth['btc_change'] = prices['bitcoin']['change']
    earth['eth'] = prices['ethereum']['price']
    earth['eth_change'] = prices['ethereum']['change']
    return earth


def fetch_earth_prices():
    """Live Earth quotes — raises on any network problem."""
    ids = ','.join(meta['id'] for meta in EARTH_COINS)
    url = COINGECKO_URL.format(ids=ids)
    with urllib.request.urlopen(url, timeout=3) as response:
        payload = json.load(response)
    prices = {}
    for meta in EARTH_COINS:
        quote = payload[meta['id']]
        prices[meta['id']] = {
            'price': Decimal(str(quote['usd'])),
            'change': Decimal(str(quote['usd_24h_change'])),
            'mcap': Decimal(str(quote.get('usd_market_cap', 0))),
        }
    return _finalize(prices, 'live')


def get_earth_prices():
    cached = cache.get(CACHE_KEY)
    if cached:
        return cached
    try:
        prices = fetch_earth_prices()
    except Exception:  # network down, rate limited, malformed payload…
        prices = _finalize({k: dict(v) for k, v in FALLBACK.items()}, 'fallback')
    cache.set(CACHE_KEY, prices, CACHE_TTL)
    return prices


def trx_price(earth):
    """Headline TerraX price: 1.25 x Bitcoin."""
    return (earth['btc'] * BTC_PEG).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)


def trx_change(earth):
    """TerraX tracks Bitcoin's daily move with a beta of 1.25."""
    return (earth['btc_change'] * BETA).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP)


def trx_series(price, change, points=48):
    """Deterministic 24h walk for the chart (stable within the hour)."""
    seed = f'{datetime.now(timezone.utc):%Y-%m-%d-%H}'
    rnd = random.Random(seed)
    start = price / (Decimal('1') + change / Decimal('100'))
    if start <= 0:
        start = price
    values = []
    step = (price - start) / Decimal(points - 1)
    swing = price * Decimal('0.004')
    current = start
    for _ in range(points):
        noise = Decimal(str(round(rnd.uniform(-1, 1), 4))) * swing
        values.append((current + noise).quantize(USD_QUANTUM))
        current += step
    values[0] = start.quantize(USD_QUANTUM)
    values[-1] = price
    return values


def chart_paths(values, width=640, height=180, pad=14):
    """SVG path data for the sparkline + its area fill."""
    lo, hi = min(values), max(values)
    span = (hi - lo) or Decimal('1')

    def xy(index, value):
        x = pad + Decimal(width - 2 * pad) * Decimal(index) / Decimal(max(len(values) - 1, 1))
        frac = (value - lo) / span
        y = Decimal(height - pad) - frac * Decimal(height - 2 * pad)
        return round(float(x), 1), round(float(y), 1)

    points = [xy(i, v) for i, v in enumerate(values)]
    line = 'M ' + ' L '.join(f'{x} {y}' for x, y in points)
    base = float(height - pad)
    area = (
        f'M {points[0][0]} {base} L '
        + ' L '.join(f'{x} {y}' for x, y in points)
        + f' L {points[-1][0]} {base} Z'
    )
    return line, area, lo, hi


def get_market():
    """Everything the market page needs, in one shot."""
    earth = get_earth_prices()
    price = trx_price(earth)
    change = trx_change(earth)
    series = trx_series(price, change)
    line, area, lo, hi = chart_paths(series)

    # Per-coin rows: declared pegs for BTC/ETH, live multiple for the rest.
    coins = []
    for meta in EARTH_COINS:
        data = earth['prices'][meta['id']]
        if meta['id'] == 'bitcoin':
            buys = BTC_PEG
        elif meta['id'] == 'ethereum':
            buys = ETH_PEG
        else:
            buys = price / data['price']
        coins.append({
            **meta,
            'price': data['price'],
            'change': data['change'],
            'mcap': data['mcap'],
            'buys': buys,
        })

    return {
        **earth,
        'trx_price': price,
        'trx_change': change,
        'btc_peg': BTC_PEG,
        'eth_peg': ETH_PEG,
        'fee': EXCHANGE_FEE,
        'coins': coins,
        'series': series,
        'chart_line': line,
        'chart_area': area,
        'series_low': lo,
        'series_high': hi,
    }