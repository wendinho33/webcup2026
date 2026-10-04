import os

from webcup2026.wsgi import application


def _ensure_superuser():
    """Create/update the admin superuser in the *runtime* database.

    The build step also runs ``manage.py ensure_superuser``, but on Hodifly the
    persisted SQLite file can be laid down around the build, so the account the
    build creates may not be the one the running app serves. Making sure here —
    after Django is set up and against the live database — closes that gap.
    Idempotent, so it is safe to run on every Passenger worker start.
    """
    try:
        from django.core.management import call_command
        call_command('ensure_superuser', verbosity=0)
    except Exception:
        # Never let superuser bootstrapping prevent the app from starting.
        pass


_ensure_superuser()
