import random
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_noop
from datetime import timedelta

from .transit import WELCOME_BONUS

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
    # TerraX wallet
    trx_balance = models.DecimalField(
        max_digits=14, decimal_places=6, default=Decimal('0'),
    )
    usd_balance = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('5000'),
    )
    priority = models.BooleanField(default=False)
    is_agent = models.BooleanField(
        default=False,
        help_text='May answer other Novarians in Terra Chat.',
    )
    date_of_birth = models.DateField(
        null=True, blank=True,
        help_text='On file for pension eligibility.',
    )
    terra_watch = models.BooleanField(
        default=False,
        help_text='Terra Watch health monitor paired (50 TRX).',
    )
    avatar = models.ImageField(
        upload_to='avatars/%Y/%m/',
        blank=True,
        help_text='Passenger photo shown in Mission Control and chat.',
    )
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


class Transaction(models.Model):
    """A settled TerraX trade or service purchase."""

    KIND_CHOICES = [
        ('buy', 'Buy'),
        ('sell', 'Sell'),
        ('service', 'Service'),
        ('tax', 'Tax'),
        ('pension', 'Pension'),
        ('fare', 'Fare'),
        ('bonus', 'Bonus'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='transactions',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    trx = models.DecimalField(
        max_digits=14, decimal_places=6,
        help_text='Signed TerraX amount (negative = spent).',
    )
    usd = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Signed Earth-credit amount (negative = spent).',
    )
    price_usd = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=140, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()} {self.trx} TRX · {self.note}'


class TaxBill(models.Model):
    """One fiscal-period civic levy on a Novarian's wallet."""

    STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tax_bills',
    )
    code = models.CharField(max_length=16)  # e.g. FY2026-Q4
    amount_trx = models.DecimalField(max_digits=12, decimal_places=6)
    status = models.CharField(
        max_length=8, choices=STATUS_CHOICES, default='unpaid',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'code'], name='unique_tax_bill_per_period',
            ),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} · {self.amount_trx} TRX · {self.status}'


class CivicRequest(models.Model):
    """A service request filed at the government portal (road, waste,
    medical) with a tracking code and an age-driven status."""

    CATEGORY_CHOICES = [
        ('road', 'Road upgrade'),
        ('waste', 'Waste management'),
        ('medical', 'Medical service'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='civic_requests',
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES)
    sector = models.CharField(max_length=20, choices=SECTOR_CHOICES)
    location = models.CharField(max_length=140)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    # category → (prefix, status ladder as (max_hours, label, slug))
    _LADDERS = {
        'road': [(1, 'Received', 'received'), (6, 'Under review', 'review'),
                 (24, 'Approved', 'approved'),
                 (float('inf'), 'Scheduled', 'scheduled')],
        'waste': [(1, 'Received', 'received'), (4, 'Under review', 'review'),
                  (12, 'Route planned', 'approved'),
                  (float('inf'), 'Pickup scheduled', 'scheduled')],
        'medical': [(0.5, 'Received', 'received'), (2, 'Triaged', 'review'),
                    (8, 'Care team assigned', 'approved'),
                    (float('inf'), 'Visit scheduled', 'scheduled')],
    }
    _PREFIXES = {'road': 'GR', 'waste': 'WM', 'medical': 'MD'}

    @property
    def tracking(self):
        return f'{self._PREFIXES[self.category]}-{self.id:04d}'

    @property
    def age_hours(self):
        return (timezone.now() - self.created_at).total_seconds() / 3600

    @property
    def status_label(self):
        for max_hours, label, _ in self._LADDERS[self.category]:
            if self.age_hours < max_hours:
                return label
        return self._LADDERS[self.category][-1][1]

    @property
    def status_slug(self):
        for max_hours, _, slug in self._LADDERS[self.category]:
            if self.age_hours < max_hours:
                return slug
        return self._LADDERS[self.category][-1][2]

    def __str__(self):
        return f'{self.tracking} · {self.location}'


class Traveler(models.Model):
    """A fare-paying passenger on a Novarian's account (self or family)."""

    RELATION_CHOICES = [
        ('self', 'Self'),
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('elder', 'Elder'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='travelers',
    )
    name = models.CharField(max_length=60)
    relation = models.CharField(max_length=10, choices=RELATION_CHOICES, default='self')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    @property
    def is_child(self):
        return self.relation == 'child'

    def __str__(self):
        return f'{self.name} ({self.get_relation_display()})'


class FareTicket(models.Model):
    """A paid bus/train fare, presented as a QR code at the receiver."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tickets',
    )
    traveler = models.ForeignKey(
        Traveler,
        on_delete=models.CASCADE,
        related_name='tickets',
    )
    route_id = models.CharField(max_length=8)       # B1, T1 …
    route_name = models.CharField(max_length=80)
    kind = models.CharField(max_length=8)           # bus / train
    destination = models.CharField(max_length=80)
    departure = models.DateTimeField()
    fare_trx = models.DecimalField(max_digits=12, decimal_places=6)
    code = models.CharField(max_length=32, unique=True)
    used = models.BooleanField(default=False)
    paid_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-departure']

    @property
    def payload(self):
        """URI encoded in the QR code, read by the bus/train receiver."""
        return f'terranova://ticket/{self.code}'

    @property
    def qr_svg(self):
        import qrcode
        from qrcode.image.svg import SvgPathImage
        from django.utils.safestring import mark_safe

        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=1,
            border=2,
            image_factory=SvgPathImage,
        )
        qr.add_data(self.payload)
        qr.make(fit=True)
        svg = qr.make_image().to_string()
        if isinstance(svg, bytes):
            svg = svg.decode('utf-8')
        return mark_safe(svg)

    @property
    def status(self):
        if self.used:
            return 'boarded'
        if timezone.now() > self.departure + timedelta(minutes=30):
            return 'expired'
        return 'valid'

    @property
    def status_label(self):
        return {
            'valid': 'Show at boarding',
            'boarded': 'Boarded · scanned',
            'expired': 'Departed',
        }[self.status]

    def __str__(self):
        return f'{self.route_id} · {self.traveler.name} · {self.code[:8]}'


class ChatThread(models.Model):
    """A Terra Chat conversation between a Novarian and Terra AI / agents."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('ai_handling', 'Terra AI handling'),
        ('escalated', 'Novarian agent assigned'),
        ('resolved', 'Resolved'),
    ]
    KIND_CHOICES = [
        ('general', 'General'),
        ('issue', 'Issue'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_threads',
    )
    subject = models.CharField(max_length=120)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='general')
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default='open',
    )
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='chat_assigned',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'#{self.id} · {self.subject}'

    @property
    def tracking(self):
        """Human-friendly signal id, e.g. TN-0042."""
        return f'TN-{self.id:04d}'


class ChatMessage(models.Model):
    """One line in a Terra Chat thread."""

    ROLE_CHOICES = [
        ('user', 'Novarian'),
        ('ai', 'Terra AI'),
        ('agent', 'Novarian agent'),
        ('system', 'System'),
    ]

    thread = models.ForeignKey(
        ChatThread,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='chat_messages',
    )
    role = models.CharField(max_length=8, choices=ROLE_CHOICES, default='user')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    @property
    def display_name(self):
        if self.role == 'ai':
            return 'Terra AI'
        if self.role == 'system':
            return 'System'
        if self.author:
            return self.author.get_full_name() or self.author.username
        return 'Novarian'

    def __str__(self):
        return f'{self.get_role_display()}: {self.body[:40]}'


class WeatherAlert(models.Model):
    """One day of the rolling Terra Nova heat simulation.

    Generated idempotently for today .. today+7 so Novarian devices have at
    least a week of temperature-rise notifications to receive.
    """

    SEVERITY_CHOICES = [
        ('elevated', 'Elevated'),
        ('high', 'High'),
        ('extreme', 'Extreme'),
    ]

    day = models.DateField(unique=True)
    kind = models.CharField(max_length=16, default='heat')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    temp_c = models.DecimalField(max_digits=5, decimal_places=1)
    anomaly = models.DecimalField(max_digits=4, decimal_places=1)
    headline = models.CharField(max_length=120)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['day']

    def __str__(self):
        return f'{self.day} · {self.severity} · {self.temp_c}°C'


class NewsItem(models.Model):
    """One dispatch from the Terra Nova newsroom (the News section)."""

    CATEGORY_CHOICES = [
        ('expedition', gettext_noop('Expedition')),
        ('weather', gettext_noop('Weather')),
        ('market', gettext_noop('Market')),
        ('transport', gettext_noop('Transport')),
        ('civic', gettext_noop('Civic')),
        ('health', gettext_noop('Health')),
        ('science', gettext_noop('Science')),
    ]

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default='expedition')
    summary = models.CharField(
        max_length=300,
        help_text='One-line standfirst shown on the news cards.',
    )
    body = models.TextField(help_text='Article body; blank lines separate paragraphs.')
    source = models.CharField(
        max_length=80,
        default='Terra Nova Newsroom',
        help_text='Byline or wire service shown on the article.',
    )
    is_featured = models.BooleanField(
        default=False,
        help_text='Promoted to the lead story on the News page.',
    )
    published_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return f'{self.get_category_display()} · {self.title}'

    @property
    def reading_minutes(self):
        """Rough reading time — 200 words per minute, minimum one."""
        return max(1, len(self.body.split()) // 200)


class NewsComment(models.Model):
    """One reader comment under a dispatch (the News comment section)."""

    item = models.ForeignKey(
        NewsItem,
        on_delete=models.CASCADE,
        related_name='comments',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='news_comments',
    )
    body = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.user} · {self.item_id}: {self.body[:40]}'


class Feedback(models.Model):
    """One insight a Novarian files to improve Terra Nova (Feedback page)."""

    TOPIC_CHOICES = [
        ('idea', gettext_noop('Idea')),
        ('balance', gettext_noop('Balance')),
        ('fault', gettext_noop('Fault')),
        ('content', gettext_noop('Story & content')),
        ('other', gettext_noop('Other')),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='feedbacks',
    )
    topic = models.CharField(max_length=12, choices=TOPIC_CHOICES, default='idea')
    body = models.CharField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} · {self.get_topic_display()}: {self.body[:40]}'


class DeviceLogin(models.Model):
    """One device (user-agent fingerprint) a Novarian signs in from.

    Two active devices are allowed; a third one triggers a security alert
    by email and in the notification centre.
    """

    ACTIVE_WINDOW = timedelta(days=30)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='devices',
    )
    fingerprint = models.CharField(max_length=64)
    user_agent = models.CharField(max_length=300, blank=True)
    ip_address = models.CharField(max_length=45, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_seen']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'fingerprint'],
                name='one_row_per_device',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} · {self.fingerprint[:8]}'

    @property
    def is_active(self):
        return self.last_seen >= timezone.now() - self.ACTIVE_WINDOW


class LoginAttempt(models.Model):
    """One rejected sign-in — counted to detect credential attacks."""

    username = models.CharField(max_length=150, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='login_attempts',
        help_text='The account the attempt targeted, when it exists.',
    )
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'failed · {self.username} · {self.ip_address or "unknown ip"}'


class Notification(models.Model):
    """An entry in the passenger-facing notification centre."""

    KIND_CHOICES = [
        ('device', 'Device'),
        ('security', 'Security'),
        ('system', 'System'),
        ('info', 'Info'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default='info')
    title = models.CharField(max_length=140)
    body = models.TextField()
    link = models.CharField(
        max_length=200, blank=True,
        help_text='Relative path opened when the notification is followed.',
    )
    is_read = models.BooleanField(default=False)
    emailed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_kind_display()} · {self.title}'

        return f'{self.day} · {self.severity} · {self.temp_c}°C'



class AgentRating(models.Model):
    """One passenger's rating of a Novarian agent (from the account centre)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_ratings_given',
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agent_ratings_received',
    )
    rating = models.PositiveSmallIntegerField(
        help_text='1 (worst) to 5 (outstanding).',
    )
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'agent'],
                name='one_rating_per_agent_pair',
            ),
        ]

    def __str__(self):
        return f'{self.rating}★ {self.user.username} → {self.agent.username}'


def ensure_profile(user, sector=None):
    """Return this Novarian's passenger record, creating it if missing.

    A brand-new wallet is funded with the 10,000 TRX welcome bonus and the
    grant is written to the ledger — exactly once, no matter whether the
    account was created through signup, the admin deck or the shell.
    """
    profile, created = Profile.objects.get_or_create(
        user=user,
        defaults={
            'sector': sector or random.choice(
                [code for code, _ in SECTOR_CHOICES],
            ),
            'trx_balance': WELCOME_BONUS,
        },
    )
    if created:
        Transaction.objects.create(
            user=user,
            kind='bonus',
            trx=WELCOME_BONUS,
            usd=Decimal('0.00'),
            price_usd=Decimal('0.00'),
            note='Welcome bonus · Expedition 01',
        )
    return profile
