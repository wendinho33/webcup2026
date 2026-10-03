from django.apps import AppConfig


class TerraConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'terra'
    verbose_name = 'Terra Nova'

    def ready(self):
        from . import receivers  # noqa: F401 — connects auth signal handlers
