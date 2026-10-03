import random

from django.conf import settings
from django.db import models

SECTOR_CHOICES = [
    ('aurelia', 'Aurelia Basin'),
    ('vermilion', 'Vermilion Steps'),
    ('glasslands', 'The Glass Tundra'),
    ('pelagos', 'Pelagos Deep'),
]

_CALLSIGN_PREFIXES = [
    'AURORA', 'VEGA', 'ORION', 'LYRA', 'HALO', 'NOVA', 'SIRIUS', 'ATLAS',
    'KEPLER', 'HELIX', 'ECHO', 'DRIFT', 'MERIDIAN', 'LUMEN',
]


class Profile(models.Model):
    """Passenger record attached to every Terra Nova account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    callsign = models.CharField(max_length=24, unique=True, editable=False)
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES, default='aurelia')
    tagline = models.CharField(max_length=140, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.callsign} · {self.user.username}'

    @classmethod
    def make_callsign(cls):
        for _ in range(60):
            candidate = f'{random.choice(_CALLSIGN_PREFIXES)}-{random.randint(10, 99)}'
            if not cls.objects.filter(callsign=candidate).exists():
                return candidate
        return f'EXPEDITION-{random.randint(1000, 9999)}'

    @property
    def sector_name(self):
        return self.get_sector_display()

    def save(self, *args, **kwargs):
        if not self.callsign:
            self.callsign = self.make_callsign()
        super().save(*args, **kwargs)
