from django.conf import settings
from django.urls import reverse


def notifications(request):
    """Unread notification count for the nav bell (passenger pages only)."""
    if getattr(request, 'user', None) and request.user.is_authenticated:
        from terra.models import Notification

        count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
    else:
        count = 0
    return {'unread_notifications': count}


VALID_TIERS = ('full', 'balanced', 'lite')


def net_tier(request):
    """Connection tier published by static/js/net.js via the tn_net cookie.

    'lite' (≤ 512 kbps or Save-Data) drops decorative blocks server-side;
    'balanced' (≤ 1 Mbps) keeps pages but skips background polling in JS.
    """
    raw = request.COOKIES.get('tn_net', '')
    tier = raw if raw in VALID_TIERS else 'full'
    return {'net_tier': tier, 'is_lite': tier == 'lite'}


def webpush(request):
    """VAPID public key + subscription endpoint for the push UI."""
    conf = getattr(settings, 'WEBPUSH_SETTINGS', {})
    return {
        'vapid_public_key': conf.get('VAPID_PUBLIC_KEY', ''),
        'webpush_save_url': reverse('save_webpush_info'),
    }


def tutorial(request):
    """Whether to surface the first-login tour overlay."""
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        from terra.models import Profile

        try:
            return {'show_tutorial': not user.profile.tutorial_seen}
        except Profile.DoesNotExist:
            # No profile yet (e.g. a fresh admin/shell account): first login.
            return {'show_tutorial': True}
    return {'show_tutorial': False}
