"""Terra Nova admin — the Control Deck.

A fully re-branded, charted, precise Django admin site:

* ``TerraAdminSite`` renders a live dashboard (KPIs, seven SVG charts,
  merged signals feed) on the index — see ``terra.admin_dashboard``;
* every registry has been tuned for precise operation: searchable,
  filterable lists with exact amounts, computed stages and one-click
  actions;
* the TerraX ledger is immutable (view + CSV export only).

The site keeps the ``admin`` name so every ``admin:…`` URL (LogEntry
links, shortcuts) keeps working.
"""

import csv
import io
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html

from .admin_dashboard import dashboard_context
from .models import (
    AgentRating,
    ChatMessage,
    ChatThread,
    CivicRequest,
    DeviceLogin,
    FareTicket,
    LoginAttempt,
    Notification,
    Profile,
    TaxBill,
    Transaction,
    Traveler,
    WeatherAlert,
)

_TONES = {
    'aurelia': 'solar', 'vermilion': 'solar2', 'glasslands': 'ice',
    'pelagos': 'mint',
    'paid': 'mint', 'unpaid': 'solar2',
    'open': 'ice', 'ai_handling': 'solar', 'escalated': 'solar2',
    'resolved': 'mint',
    'elevated': 'ice', 'high': 'solar', 'extreme': 'solar2',
    'buy': 'mint', 'sell': 'solar2', 'service': 'ice', 'tax': 'solar',
    'pension': 'ice', 'fare': 'solar', 'bonus': 'mint',
    'valid': 'mint', 'boarded': 'solar', 'expired': 'dim',
    'received': 'ice', 'review': 'solar', 'approved': 'mint',
    'scheduled': 'dim',
    'road': 'ice', 'waste': 'mint', 'medical': 'solar2',
    'self': 'ice', 'spouse': 'solar', 'child': 'mint', 'elder': 'ice',
    'general': 'ice', 'issue': 'solar2',
    'user': 'ice', 'ai': 'mint', 'agent': 'solar2', 'system': 'dim',
    'bus': 'mint', 'train': 'ice',
    'device': 'ice', 'security': 'solar2', 'info': 'dim',
}


def chip(text, key):
    """Status/choice pill themed by the admin stylesheet."""
    return format_html(
        '<span class="t-chip t-chip--{}">{}</span>',
        _TONES.get(key, 'dim'), text,
    )


class TerraAdminSite(admin.AdminSite):
    """The Terra Nova Control Deck admin site."""

    site_header = 'Terra Nova · Mission Control'
    site_title = 'Terra Nova Admin'
    index_title = 'Control Deck'
    index_template = 'admin/index.html'
    enable_nav_sidebar = True

    def index(self, request, extra_context=None):
        context = extra_context or {}
        context.update(dashboard_context())
        return super().index(request, context)


terra_admin_site = TerraAdminSite(name='admin')


# ── People ────────────────────────────────────────────────────────────
class ProfileInline(admin.StackedInline):
    model = Profile
    fk_name = 'user'
    can_delete = False
    extra = 0
    readonly_fields = ('callsign', 'created_at')
    fields = (
        'callsign', 'sector', 'tagline', 'trx_balance', 'usd_balance',
        'priority', 'is_agent', 'date_of_birth', 'terra_watch', 'created_at',
    )


class TerraUserAdmin(BaseUserAdmin):
    """Crew registry with the wallet record inline."""
    inlines = [ProfileInline]
    list_display = ('username', 'email', 'first_name', 'is_staff',
                    'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'date_joined')
    search_fields = ('username', 'first_name', 'email')
    ordering = ('-date_joined',)
    list_per_page = 30


class ProfileAdmin(admin.ModelAdmin):
    list_display = ('callsign', 'passenger', 'sector_chip', 'trx', 'usd',
                    'priority', 'is_agent', 'terra_watch', 'created_at')
    list_filter = ('sector', 'terra_watch', 'is_agent', 'priority')
    search_fields = ('callsign', 'user__username', 'user__email')
    readonly_fields = ('callsign', 'created_at')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    list_per_page = 30
    actions = ('pair_watch', 'unpair_watch')

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Sector', ordering='sector')
    def sector_chip(self, obj):
        return chip(obj.get_sector_display(), obj.sector)

    @admin.display(description='TRX balance', ordering='trx_balance')
    def trx(self, obj):
        return f'{obj.trx_balance:,.4f}'

    @admin.display(description='Credits (USD)', ordering='usd_balance')
    def usd(self, obj):
        return f'{obj.usd_balance:,.2f}'

    @admin.action(description='Pair Terra Watch on selected wallets (50 TRX)')
    def pair_watch(self, request, queryset):
        n = queryset.update(terra_watch=True)
        self.message_user(request, f'{n} Terra Watch monitor(s) paired.')

    @admin.action(description='Unpair Terra Watch from selected wallets')
    def unpair_watch(self, request, queryset):
        n = queryset.update(terra_watch=False)
        self.message_user(request, f'{n} Terra Watch monitor(s) unpaired.')


# ── Terra Chat ────────────────────────────────────────────────────────
class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('author', 'role', 'body', 'created_at')
    fields = readonly_fields
    can_delete = False
    show_change_link = True


class ChatThreadAdmin(admin.ModelAdmin):
    list_display = ('tracking', 'subject', 'passenger', 'kind_chip',
                    'status_chip', 'agent', 'messages', 'updated_at')
    list_filter = ('status', 'kind', 'assigned_agent')
    search_fields = ('subject', 'user__username', 'assigned_agent__username')
    date_hierarchy = 'updated_at'
    list_select_related = ('user', 'assigned_agent')
    list_per_page = 30
    inlines = [ChatMessageInline]
    actions = ('resolve_threads', 'escalate_threads')
    ordering = ('-updated_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            n_messages=Count('messages'),
        )

    @admin.display(description='Signal')
    def tracking(self, obj):
        return obj.tracking

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Kind')
    def kind_chip(self, obj):
        return chip(obj.get_kind_display(), obj.kind)

    @admin.display(description='Status', ordering='status')
    def status_chip(self, obj):
        return chip(obj.get_status_display(), obj.status)

    @admin.display(description='Agent', ordering='assigned_agent__username')
    def agent(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.username
        return '—'

    @admin.display(description='Msgs', ordering='n_messages')
    def messages(self, obj):
        return obj.n_messages

    @admin.action(description='Mark selected threads resolved')
    def resolve_threads(self, request, queryset):
        n = queryset.update(status='resolved')
        self.message_user(request, f'{n} thread(s) resolved.')

    @admin.action(description='Escalate selected threads to Novarian agents')
    def escalate_threads(self, request, queryset):
        n = queryset.update(status='escalated')
        self.message_user(request, f'{n} thread(s) escalated.')


class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('short_body', 'thread', 'role_chip', 'author_name',
                    'created_at')
    list_filter = ('role',)
    search_fields = ('body', 'thread__subject', 'author__username')
    date_hierarchy = 'created_at'
    list_select_related = ('thread', 'author')
    list_per_page = 50
    ordering = ('-created_at',)

    @admin.display(description='Message')
    def short_body(self, obj):
        text = obj.body.replace('\n', ' ')
        return text if len(text) <= 60 else text[:57] + '…'

    @admin.display(description='Role')
    def role_chip(self, obj):
        return chip(obj.get_role_display(), obj.role)

    @admin.display(description='Author')
    def author_name(self, obj):
        if obj.author:
            return obj.author.username
        return '—'


# ── Ledger & fiscal ───────────────────────────────────────────────────
class TransactionAdmin(admin.ModelAdmin):
    """Immutable TerraX ledger: view + CSV export, never edit."""

    list_display = ('created_at', 'passenger', 'kind_chip', 'trx', 'usd',
                    'price', 'note')
    list_filter = ('kind', 'created_at')
    search_fields = ('user__username', 'note')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    list_per_page = 40
    ordering = ('-created_at',)
    actions = ('export_csv',)
    readonly_fields = ('user', 'kind', 'trx', 'usd', 'price_usd', 'note',
                       'created_at')
    fields = readonly_fields

    def has_add_permission(self, request):
        return False  # entries only originate from site events

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Kind', ordering='kind')
    def kind_chip(self, obj):
        return chip(obj.get_kind_display(), obj.kind)

    @admin.display(description='TRX (signed)', ordering='trx')
    def trx(self, obj):
        return f'{obj.trx:+,.4f}'

    @admin.display(description='Credits (signed)', ordering='usd')
    def usd(self, obj):
        return f'{obj.usd:+,.2f}'

    @admin.display(description='Unit price', ordering='price_usd')
    def price(self, obj):
        return f'{obj.price_usd:,.2f}'

    @admin.action(description='Export selected rows to CSV')
    def export_csv(self, request, queryset):
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['created_at', 'user', 'kind', 'trx', 'usd',
                         'price_usd', 'note'])
        for t in queryset.select_related('user').order_by('-created_at'):
            writer.writerow([
                t.created_at.isoformat(), t.user.username, t.kind,
                t.trx, t.usd, t.price_usd, t.note,
            ])
        response = HttpResponse(buf.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = (
            'attachment; filename="terrax-ledger.csv"'
        )
        return response


class TaxBillAdmin(admin.ModelAdmin):
    list_display = ('code', 'passenger', 'amount', 'status_chip',
                    'paid_at', 'created_at')
    list_filter = ('status', 'code')
    search_fields = ('user__username', 'code')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    actions = ('mark_paid',)

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Amount', ordering='amount_trx')
    def amount(self, obj):
        return f'{obj.amount_trx:,.4f} TRX'

    @admin.display(description='Status', ordering='status')
    def status_chip(self, obj):
        return chip(obj.get_status_display(), obj.status)

    @admin.action(description='Mark selected bills paid (timestamped now)')
    def mark_paid(self, request, queryset):
        n = queryset.filter(status='unpaid').update(
            status='paid', paid_at=timezone.now(),
        )
        self.message_user(request, f'{n} bill(s) settled.')


# ── Government portal ─────────────────────────────────────────────────
_STAGE_SLUGS = ('received', 'review', 'approved', 'scheduled')
_THRESHOLDS = {
    cat: [h for h, _label, _slug in ladder[:-1]]
    for cat, ladder in CivicRequest._LADDERS.items()
}


def _stage_q(slug):
    """Translate an age-driven stage into a real database predicate."""
    now = timezone.now()
    idx = _STAGE_SLUGS.index(slug)
    combined = Q()
    for cat, thresholds in _THRESHOLDS.items():
        cat_q = Q(category=cat)
        if idx == 0:
            cat_q &= Q(created_at__gte=now - timedelta(hours=thresholds[0]))
        elif idx >= len(thresholds):
            cat_q &= Q(created_at__lt=now - timedelta(hours=thresholds[-1]))
        else:
            cat_q &= Q(created_at__lt=now - timedelta(hours=thresholds[idx - 1]))
            cat_q &= Q(created_at__gte=now - timedelta(hours=thresholds[idx]))
        combined |= cat_q
    return combined


class CivicStageFilter(admin.SimpleListFilter):
    """Filter by the live, age-derived pipeline stage (SQL, not Python)."""

    title = 'live stage'
    parameter_name = 'stage'

    def lookups(self, request, model_admin):
        return [
            ('received', 'Received'),
            ('review', 'Under review'),
            ('approved', 'Approved'),
            ('scheduled', 'Scheduled'),
        ]

    def queryset(self, request, queryset):
        if self.value() in _STAGE_SLUGS:
            return queryset.filter(_stage_q(self.value()))
        return queryset


class CivicRequestAdmin(admin.ModelAdmin):
    list_display = ('tracking', 'category_chip', 'stage_chip', 'passenger',
                    'sector', 'location', 'age', 'created_at')
    list_filter = (CivicStageFilter, 'category', 'sector')
    search_fields = ('location', 'detail', 'user__username')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    readonly_fields = ('tracking', 'status_label', 'age_hours')
    ordering = ('-created_at',)
    list_per_page = 30

    @admin.display(description='Tracking')
    def tracking(self, obj):
        return obj.tracking

    @admin.display(description='Category')
    def category_chip(self, obj):
        return chip(obj.get_category_display(), obj.category)

    @admin.display(description='Stage (age-driven)')
    def stage_chip(self, obj):
        return chip(obj.status_label, obj.status_slug)

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Age')
    def age(self, obj):
        return f'{obj.age_hours:.1f} h'


class TravelerAdmin(admin.ModelAdmin):
    list_display = ('name', 'relation_chip', 'passenger', 'passes',
                    'created_at')
    list_filter = ('relation',)
    search_fields = ('name', 'user__username')
    list_select_related = ('user',)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(n_tickets=Count('tickets'))

    @admin.display(description='Relation')
    def relation_chip(self, obj):
        return chip(obj.get_relation_display(), obj.relation)

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Passes', ordering='n_tickets')
    def passes(self, obj):
        return obj.n_tickets


# ── Transport ─────────────────────────────────────────────────────────
class FareStatusFilter(admin.SimpleListFilter):
    title = 'boarding state'
    parameter_name = 'bstate'

    def lookups(self, request, model_admin):
        return [
            ('valid', 'Valid (show at boarding)'),
            ('boarded', 'Boarded (scanned)'),
            ('expired', 'Departed'),
        ]

    def queryset(self, request, queryset):
        cutoff = timezone.now() - timedelta(minutes=30)
        if self.value() == 'valid':
            return queryset.filter(used=False, departure__gte=cutoff)
        if self.value() == 'boarded':
            return queryset.filter(used=True)
        if self.value() == 'expired':
            return queryset.filter(used=False, departure__lt=cutoff)
        return queryset


class FareTicketAdmin(admin.ModelAdmin):
    list_display = ('code_short', 'route', 'kind_chip', 'traveler_name',
                    'destination', 'departure', 'fare', 'status_chip')
    list_filter = (FareStatusFilter, 'kind')
    search_fields = ('code', 'route_id', 'route_name', 'destination',
                     'traveler__name', 'user__username')
    date_hierarchy = 'departure'
    list_select_related = ('user', 'traveler')
    readonly_fields = ('code', 'paid_at', 'payload', 'qr_svg')
    actions = ('mark_boarded',)
    ordering = ('-departure',)
    list_per_page = 30

    @admin.display(description='Code')
    def code_short(self, obj):
        return f'{obj.code[:10]}…' if len(obj.code) > 10 else obj.code

    @admin.display(description='Route', ordering='route_id')
    def route(self, obj):
        return f'{obj.route_id} · {obj.route_name}'

    @admin.display(description='Kind')
    def kind_chip(self, obj):
        return chip(str(obj.kind).title(), obj.kind)

    @admin.display(description='Traveler')
    def traveler_name(self, obj):
        return obj.traveler.name

    @admin.display(description='Fare', ordering='fare_trx')
    def fare(self, obj):
        return f'{obj.fare_trx:,.4f} TRX'

    @admin.display(description='State')
    def status_chip(self, obj):
        return chip(obj.status_label, obj.status)

    @admin.action(description='Scan selected passes (mark boarded)')
    def mark_boarded(self, request, queryset):
        n = queryset.update(used=True)
        self.message_user(request, f'{n} pass(es) scanned at boarding.')


# ── Weather deck ──────────────────────────────────────────────────────
class WeatherAlertAdmin(admin.ModelAdmin):
    list_display = ('day', 'severity_chip', 'temp', 'anomaly', 'headline')
    list_filter = ('severity',)
    search_fields = ('headline', 'message')
    date_hierarchy = 'day'
    readonly_fields = ('created_at',)
    ordering = ('-day',)

    @admin.display(description='Severity')
    def severity_chip(self, obj):
        return chip(obj.get_severity_display(), obj.severity)

    @admin.display(description='Temp')
    def temp(self, obj):
        return f'{obj.temp_c} °C'

    @admin.display(description='Anomaly')
    def anomaly(self, obj):
        return f'{obj.anomaly:+} °C'


# ── Security watch ─────────────────────────────────────────────────────
class DeviceLoginAdmin(admin.ModelAdmin):
    list_display = ('passenger', 'short_fp', 'ip', 'first_seen', 'last_seen',
                    'active_chip')
    search_fields = ('user__username', 'fingerprint', 'ip_address',
                     'user_agent')
    ordering = ('-last_seen',)
    readonly_fields = ('fingerprint', 'first_seen', 'last_seen')

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Device')
    def short_fp(self, obj):
        return f'{obj.fingerprint[:12]}…'

    @admin.display(description='IP')
    def ip(self, obj):
        return obj.ip_address or '—'

    @admin.display(description='Status')
    def active_chip(self, obj):
        return chip('Active' if obj.is_active else 'Stale',
                    'mint' if obj.is_active else 'dim')


class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('username', 'matched_chip', 'ip', 'agent', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('username', 'ip_address', 'user_agent')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('username', 'user', 'ip_address', 'user_agent',
                       'created_at')

    @admin.display(description='Account')
    def matched_chip(self, obj):
        if obj.user_id:
            return chip('Matched', 'solar')
        return chip('Unknown', 'dim')

    @admin.display(description='IP')
    def ip(self, obj):
        return obj.ip_address or '—'

    @admin.display(description='Agent')
    def agent(self, obj):
        return (obj.user_agent or '—')[:40]


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('kind_chip', 'short_title', 'passenger', 'read_chip',
                    'emailed_chip', 'created_at')
    list_filter = ('kind', 'is_read', 'emailed')
    search_fields = ('title', 'body', 'user__username')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    readonly_fields = ('created_at',)

    @admin.display(description='Kind')
    def kind_chip(self, obj):
        return chip(obj.get_kind_display(), obj.kind)

    @admin.display(description='Signal', ordering='title')
    def short_title(self, obj):
        return obj.title[:60]

    @admin.display(description='Passenger', ordering='user__username')
    def passenger(self, obj):
        return obj.user.username

    @admin.display(description='Read')
    def read_chip(self, obj):
        return chip('Read' if obj.is_read else 'Unread',
                    'dim' if obj.is_read else 'solar')

    @admin.display(description='Emailed')
    def emailed_chip(self, obj):
        return chip('Sent' if obj.emailed else 'Local',
                    'mint' if obj.emailed else 'dim')


# ── Account centre ────────────────────────────────────────────────────
class AgentRatingAdmin(admin.ModelAdmin):
    list_display = ('stars', 'agent_name', 'rater', 'short_comment',
                    'updated_at')
    list_filter = ('rating',)
    search_fields = ('agent__username', 'user__username', 'comment')
    date_hierarchy = 'updated_at'
    ordering = ('-updated_at',)
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Stars')
    def stars(self, obj):
        # map to _TONES keys: 5/4 → mint, 3 → ice, 2 → solar, 1 → solar2
        tone = {5: 'paid', 4: 'valid', 3: 'received',
                2: 'review', 1: 'unpaid'}[obj.rating]
        return chip('★' * obj.rating + '☆' * (5 - obj.rating), tone)

    @admin.display(description='Agent', ordering='agent__username')
    def agent_name(self, obj):
        return obj.agent.username

    @admin.display(description='From', ordering='user__username')
    def rater(self, obj):
        return obj.user.username

    @admin.display(description='Comment')
    def short_comment(self, obj):
        return (obj.comment or '—')[:50]


# ── Registration ──────────────────────────────────────────────────────
terra_admin_site.register(User, TerraUserAdmin)
terra_admin_site.register(Profile, ProfileAdmin)
terra_admin_site.register(Transaction, TransactionAdmin)
terra_admin_site.register(TaxBill, TaxBillAdmin)
terra_admin_site.register(CivicRequest, CivicRequestAdmin)
terra_admin_site.register(Traveler, TravelerAdmin)
terra_admin_site.register(FareTicket, FareTicketAdmin)
terra_admin_site.register(ChatThread, ChatThreadAdmin)
terra_admin_site.register(ChatMessage, ChatMessageAdmin)
terra_admin_site.register(WeatherAlert, WeatherAlertAdmin)
terra_admin_site.register(DeviceLogin, DeviceLoginAdmin)
terra_admin_site.register(LoginAttempt, LoginAttemptAdmin)
terra_admin_site.register(Notification, NotificationAdmin)
terra_admin_site.register(AgentRating, AgentRatingAdmin)
