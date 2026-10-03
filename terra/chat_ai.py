"""Terra AI — the resident intelligence that answers Novarians in Terra Chat.

A deterministic intent engine: no external API, no keys, fully testable.
`respond(text, thread)` returns (intent, reply) and the view applies the
side effects (flagging issues, escalating, resolving).
"""
import re

_WORD = r'(?:^|(?<=\s)){}(?=$|(?=\s)|[.,!?;:])'


def _hit(text, keyword):
    return re.search(_WORD.format(re.escape(keyword)), text, re.IGNORECASE) is not None


# Matched first, in order — any single keyword wins.
_PRIORITY = [
    ('confirm_resolved', [
        'solved', 'resolved', 'fixed', 'that works', 'works now',
        'all good', 'issue is gone', 'working now',
    ]),
    ('escalate', [
        'human', 'real person', 'novarian agent', 'speak to someone',
        'talk to someone', 'talk to a person', 'speak to a human',
        'representative', 'support team', 'escalate', 'agent please',
        'person please',
    ]),
    ('issue', [
        'problem', 'issue', 'bug', 'broken', 'error', 'not working',
        "doesn't work", 'doesnt work', 'cannot', "can't", 'failed',
        'failure', 'glitch', 'stuck', 'crash', 'is down', 'went down',
        'wrong', 'lost my', 'not loading', 'unusable',
    ]),
]

# Otherwise: highest keyword score wins (earlier intent wins ties).
_SCORED = [
    ('greeting', ['hello', 'hi', 'hey', 'greetings', 'good morning',
                  'good evening', 'salut', 'bonjour']),
    ('market', ['market', 'price', 'prices', 'trax', 'terrax', 'trx',
                'bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'coin',
                'crypto', 'trade', 'trading', 'buy', 'sell', 'chart',
                'peg', 'dogecoin']),
    ('wallet', ['balance', 'wallet', 'credits', 'credit', 'funds',
                'portfolio', 'money']),
    ('services', ['sector', 'callsign', 'call sign', 'priority',
                  'rename', 'transfer', 'services']),
    ('account', ['password', 'passphrase', 'login', 'log in', 'sign in',
                 'signin', 'sign up', 'signup', 'register', 'account']),
    ('passage', ['passage', 'passenger', 'expedition', 'manifest',
                 'boarding', 'launch', 'ship']),
    ('planet', ['gravity', 'oxygen', 'atmosphere', 'weather',
                'temperature', 'planet', 'biome', 'atlas', 'ocean',
                'climate', 'terra nova']),
    ('thanks', ['thank', 'thanks', 'thx', 'cheers', 'appreciate']),
]


def classify(text):
    """Best-guess intent name for a Novarian message."""
    text = (text or '').strip()
    for intent, keywords in _PRIORITY:
        if any(_hit(text, kw) for kw in keywords):
            return intent
    best, best_score = 'fallback', 0
    for intent, keywords in _SCORED:
        score = sum(1 for kw in keywords if _hit(text, kw))
        if score > best_score:
            best, best_score = intent, score
    return best


def _menu():
    return ('I can help with: signal an issue, the TerraX market and prices, '
            'your wallet, site services (sector, callsign, priority), '
            'your passage, or facts about the planet.')
def respond(text, thread):
    """Return (intent, reply) for a message in the given thread."""
    intent = classify(text)

    replies = {
        'greeting': (
            'Greetings, Novarian. I am Terra AI, the station intelligence '
            'keeping this channel open. ' + _menu() + ' What do you need?'
        ),
        'issue': (
            f'Understood — I have logged this as signal {thread.tracking}. '
            'Tell me the exact step where it breaks and anything the screen '
            'told you, and I will stay on it in this thread. If you would '
            'rather have a Novarian agent take over, press Escalate below — '
            'they will pick up this conversation directly.'
        ),
        'escalate': (
            'Of course — I am flagging this thread for the Novarian agent '
            'network now. An agent will read the history and reply here; '
            'their name will appear above their message.'
        ),
        'confirm_resolved': (
            f'Excellent — marking signal {thread.tracking} resolved. '
            'Glad it cleared. Open a new signal any time; I am on this '
            'channel every hour of the long orbit.'
        ),
        'market': (
            'TerraX markets live on the Market page (nav → Market). TRX is '
            'pegged at 1.25× Bitcoin and 5× Ethereum, Earth pairs stream '
            'live from the reference feed, and every trade costs a flat 0.5% '
            'exchange fee. You can buy and sell straight from the trading desk.'
        ),
        'wallet': (
            'Your wallet sits in Mission Control: Earth credits to trade with '
            'and your TerraX balance, plus a private ledger of every order. '
            'New passengers start with 5,000 Earth credits on the demo network.'
        ),
        'services': (
            'TerraX settles the site’s own services: Sector transfer '
            '(0.40 TRX) lets you choose your biome, Callsign rename (0.25 TRX) '
            'sets a callsign of your own, and Priority boarding (2.00 TRX) '
            'flags your manifest. All three are on the Market page under '
            'Spend TerraX.'
        ),
        'account': (
            'Passages are claimed at /signup/ and the desk opens at /login/. '
            'If you have lost your passphrase, say "problem" here and I will '
            'open a signal — an agent can help recover access.'
        ),
        'passage': (
            'Claim your passage with the sign-up form; you receive a callsign '
            'and a random sector draw the moment it is confirmed. Mission '
            'Control then shows your departure countdown, wallet and manifest.'
        ),
        'planet': (
            'Terra Nova runs at 1.02 g with a 21.4% oxygen sky, 68% ocean '
            'cover and no extinction events on record — four surveyed biomes '
            'from warm Aurelia Basin to the Pelagos Deep. The Atlas section on '
            'the home page has the full survey.'
        ),
        'thanks': (
            'Any time. I keep this channel warm — call on me whenever you '
            'need a signal, a price or a passage.'
        ),
        'fallback': (
            'I did not quite catch that. ' + _menu() + ' If something is '
            'broken, say "signal an issue" and I will open a tracking record.'
        ),
    }
    return intent, replies.get(intent, replies['fallback'])