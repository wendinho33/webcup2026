"""Security watch — device limits and credential-attack detection.

Informs the passenger two ways whenever something is off:

* a **notification** in the app's notification centre (bell in the nav);
* an **email** to the address on file (console mailer in development).

Two rules:

1. No more than ``MAX_ACTIVE_DEVICES`` devices may be active per account —
   a third one raises a *device* alert.
2. ``ATTACK_THRESHOLD`` failed sign-ins for one username inside
   ``ATTACK_WINDOW`` raise a *security* alert (credential stuffing /
   brute force).

The delivery helpers are deliberately fail-safe: a broken mailer must never
break a login, so every email is wrapped and recorded either way.
"""
import hashlib
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import DeviceLogin, LoginAttempt, Notification

MAX_ACTIVE_DEVICES = 2
ATTACK_THRESHOLD = 5
ATTACK_WINDOW = timedelta(minutes=10)

FINGERPRINT_SALT = 'terra-nova.device.v1'


def _client_ip(request):
    """Best-effort client address (proxy header when present)."""
    if request is None:
        return ''
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()[:45]
    return (request.META.get('REMOTE_ADDR') or '')[:45]


def _user_agent(request):
    if request is None:
        return ''
    return (request.META.get('HTTP_USER_AGENT') or '')[:300]


def device_fingerprint(request):
    """Stable per-device id: salted hash of the user agent."""
    raw = _user_agent(request).strip().lower() or 'unknown-device'
    return hashlib.sha256(f'{FINGERPRINT_SALT}:{raw}'.encode()).hexdigest()


def notify(user, kind, title, body, link=''):
    """Create a notification centre entry and email it when possible.

    Returns the Notification (never raises on mail failure).
    """
    emailed = False
    if user.email:
        try:
            send_mail(
                subject=f'[Terra Nova] {title}',
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
            )
            emailed = True
        except Exception:  # noqa: BLE001 — mail must not break the request
            emailed = False
    return Notification.objects.create(
        user=user,
        kind=kind,
        title=title,
        body=body,
        link=link,
        emailed=emailed,
    )


def record_login_device(request, user):
    """Track the signing-in device; alert when a third one goes active.

    Returns the created Notification or None.
    """
    if request is None or user is None or not user.is_authenticated:
        return None

    fingerprint = device_fingerprint(request)
    device, created = DeviceLogin.objects.get_or_create(
        user=user,
        fingerprint=fingerprint,
        defaults={
            'user_agent': _user_agent(request),
            'ip_address': _client_ip(request),
        },
    )
    if not created:
        # Refresh last_seen (+ ip) without clobbering first_seen.
        device.last_seen = timezone.now()
        device.ip_address = _client_ip(request) or device.ip_address
        device.save(update_fields=['last_seen', 'ip_address'])
        return None

    active = DeviceLogin.objects.filter(
        user=user,
        last_seen__gte=timezone.now() - DeviceLogin.ACTIVE_WINDOW,
    ).count()
    if active <= MAX_ACTIVE_DEVICES:
        return None

    return notify(
        user,
        kind='device',
        title=f'Sign-in from device #{active} — limit is {MAX_ACTIVE_DEVICES}',
        body=(
            f'Hello {user.get_full_name() or user.username},\n\n'
            f'A new device just signed in to your Terra Nova account and you '
            f'now have {active} active devices (allowed: '
            f'{MAX_ACTIVE_DEVICES}).\n\n'
            f'Device: {_user_agent(request) or "unknown"}\n'
            f'Address: {_client_ip(request) or "unknown"}\n'
            f'Time: {timezone.now().strftime("%d %b %Y, %H:%M UTC")}\n\n'
            f'If this was not you, sign out everywhere from the notification '
            f'centre and change your passphrase immediately.\n\n'
            f'— Mission Control Security'
        ),
        link=reverse('terra:notifications'),
    )


def record_failed_login(request, credentials):
    """Log a rejected sign-in and alert on attack patterns.

    Returns the created Notification or None.
    """
    username = str((credentials or {}).get('username') or '')[:150]
    if not username:
        return None

    from django.contrib.auth import get_user_model

    target = get_user_model().objects.filter(username=username).first()
    LoginAttempt.objects.create(
        username=username,
        user=target,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
    )
    if target is None:
        return None  # unknown account — nothing to inform

    window_start = timezone.now() - ATTACK_WINDOW
    recent = LoginAttempt.objects.filter(
        username=username,
        created_at__gte=window_start,
    ).count()
    if recent < ATTACK_THRESHOLD:
        return None

    # One alert per attack window (reset the counter to avoid spam).
    already_alerted = Notification.objects.filter(
        user=target,
        kind='security',
        created_at__gte=window_start,
    ).exists()
    if already_alerted:
        return None

    ips = (
        LoginAttempt.objects.filter(
            username=username,
            created_at__gte=window_start,
        )
        .values_list('ip_address', flat=True)
        .distinct()[:5]
    )
    ip_list = ', '.join(ip or 'unknown' for ip in ips)
    return notify(
        target,
        kind='security',
        title=f'Possible attack: {recent} failed sign-ins in 10 minutes',
        body=(
            f'Hello {target.get_full_name() or target.username},\n\n'
            f'{recent} sign-in attempts to your account were rejected in the '
            f'last 10 minutes. This can mean someone is trying to guess your '
            f'passphrase.\n\n'
            f'Addresses seen: {ip_list}\n'
            f'Time: {timezone.now().strftime("%d %b %Y, %H:%M UTC")}\n\n'
            f'If this was not you, change your passphrase immediately and '
            f'check your active devices in the notification centre.\n\n'
            f'— Mission Control Security'
        ),
        link=reverse('terra:notifications'),
    )

