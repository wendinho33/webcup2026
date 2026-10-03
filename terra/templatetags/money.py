"""Formatting filters for money, balances and percentages."""
from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def usd(value):
    """$135,562.50"""
    try:
        return f'${value:,.2f}'
    except (TypeError, ValueError):
        return value


@register.filter
def trx(value):
    """0.007339 (6dp, exchange precision)."""
    try:
        return f'{value:,.6f}'
    except (TypeError, ValueError):
        return value


@register.filter
def price(value):
    """$108,450.00 — or $0.1842 for sub-dollar coins."""
    try:
        v = Decimal(str(value))
    except (TypeError, ValueError):
        return value
    if v and abs(v) < 1:
        return f'${v:,.4f}'
    return f'${v:,.2f}'


@register.filter
def mcap(value):
    """$2.15T / $504.00B / $7.42B"""
    try:
        v = Decimal(str(value))
    except (TypeError, ValueError):
        return value
    for limit, suffix in (
        (Decimal('1000000000000'), 'T'),
        (Decimal('1000000000'), 'B'),
        (Decimal('1000000'), 'M'),
    ):
        if abs(v) >= limit:
            return f'${v / limit:,.2f}{suffix}'
    return f'${v:,.0f}'


@register.filter
def many(value):
    """Adaptive count: 1.2500 · 727.2667 · 735,953"""
    try:
        v = Decimal(str(value))
    except (TypeError, ValueError):
        return value
    if abs(v) >= 1000:
        return f'{v:,.0f}'
    if abs(v) >= 1:
        return f'{v:,.4f}'
    return f'{v:,.6f}'


@register.filter
def mul(value, arg):
    """Multiply two numbers (Decimal-safe): {{ balance|mul:price|usd }}"""
    try:
        return value * arg
    except TypeError:
        return None


@register.filter
def pct(value):
    """+2.30% / −0.72%"""
    try:
        return f'{value:+.2f}%'.replace('-', '−')
    except (TypeError, ValueError):
        return value
