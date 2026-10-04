"""Newsroom template filters — translating seeded content at render time.

The dispatches live in the database as stable English msgids
(marked with gettext_noop at seed time); the ``t`` filter resolves them
into the active language on the way to the page.
"""
from django import template
from django.utils.translation import gettext

register = template.Library()


@register.filter
def t(value):
    """Translate a stored newsroom string, falling back to itself."""
    if not value:
        return value
    return gettext(str(value))