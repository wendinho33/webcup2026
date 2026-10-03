"""Template helpers for the Terra Nova admin interface overhaul."""

from django import template

register = template.Library()

_SKIP_PARAMS = frozenset({'q', 'p', 'e', 'o', 'is_popup', 'from'})


@register.simple_tag(takes_context=True)
def without_param(context, key):
    """Current querystring with one parameter removed (filter chip ✕)."""
    request = context.get('request')
    if request is None:
        return '?'
    params = request.GET.copy()
    params.pop(key, None)
    query = params.urlencode()
    return f'?{query}' if query else '?'


@register.filter
def pretty_param(key):
    """'category__exact' -> 'Category', 'bstate' -> 'Bstate'."""
    name = str(key)
    for suffix in ('__exact', '__iexact', '__contains'):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = name.replace('__', ' ').replace('_', ' ')
    return name[:1].upper() + name[1:] if name else name


@register.inclusion_tag('tn_admin/active_filters.html', takes_context=True)
def active_filter_chips(context):
    """Removable chips describing every applied changelist filter."""
    cl = context.get('cl')
    chips = []
    if cl is not None and getattr(cl, 'has_active_filters', False):
        for name, value in cl.params.items():
            if name in _SKIP_PARAMS:
                continue
            chips.append({
                'key': pretty_param(name),
                'value': str(value),
                'href': without_param(context, name),
            })
    return {'chips': chips, 'clear_qs': getattr(cl, 'clear_all_filters_qs', None)}
