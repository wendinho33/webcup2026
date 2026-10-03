"""Web Push broadcasting for Terra Nova (django-pwa-webpush / pywebpush).

The service worker (serviceworker.js) renders whatever JSON arrives on
the `push` event: headline/title + message/body + url + tag. The helpers
here never let a dead endpoint or a missing key break a page — push is
always progressive enhancement on top of the in-page notifications.
"""
import json
import logging

from django.conf import settings

from pywebpush import WebPushException

from pwa_webpush.utils import send_to_subscription

logger = logging.getLogger(__name__)


def broadcast_push(title, message, url='/weather/', tag='terra-push', ttl=0):
    """Send one web push to every saved subscription.

    Subscriptions whose push service answers 404/410 (expired or
    unsubscribed at the browser) are pruned. Returns how many
    subscriptions accepted the message.
    """
    if not getattr(settings, 'WEBPUSH_SETTINGS', {}).get('VAPID_PRIVATE_KEY'):
        return 0

    payload = json.dumps({
        # both spellings: the service worker accepts headline/message
        # (heat alerts) and title/body (generic).
        'headline': title,
        'title': title,
        'message': message,
        'body': message,
        'url': url,
        'tag': tag,
    })

    from pwa_webpush.models import PushInformation  # after setup — local

    sent = 0
    for info in PushInformation.objects.select_related('subscription'):
        try:
            send_to_subscription(info.subscription, payload, ttl)
            sent += 1
        except WebPushException as exc:
            status = exc.status_code
            if status in (404, 410):
                # the browser revoked it — drop the dead rows (cascade).
                info.subscription.delete()
            logger.warning('web push failed (status=%s): %s', status, exc)
        except Exception:  # noqa: BLE001 — push must never break a request
            logger.exception('web push errored')
    return sent