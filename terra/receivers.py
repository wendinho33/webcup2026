"""Auth signal receivers — feed the security watch (terra.security)."""
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .security import record_failed_login, record_login_device


@receiver(user_logged_in, dispatch_uid='terra.track_login_device')
def track_login_device(sender, request, user, **kwargs):
    """Register the device and alert when a third one goes active."""
    record_login_device(request, user)


@receiver(user_login_failed, dispatch_uid='terra.track_failed_login')
def track_failed_login(sender, credentials, request, **kwargs):
    """Log the rejected attempt and alert on attack patterns."""
    record_failed_login(request, credentials)
