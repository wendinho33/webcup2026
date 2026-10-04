import json
import re
import secrets
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext
from django.views.decorators.http import require_http_methods, require_POST

from .chat_ai import respond as ai_respond
from .civic import (
    PENSION_AGE,
    PENSION_MONTHLY,
    TAX_SCHEDULE,
    TERRA_WATCH_PRICE,
    age_on,
    device_id,
    facilities_for,
    fiscal_code,
    get_or_create_tax_bill,
    months_since_claim,
    pension_state,
    social_security,
    vitals,
    waste_schedule,
)
from .forms import (
    AccountForm,
    AvatarForm,
    BuyForm,
    LoginForm,
    RatingForm,
    SellForm,
    SignupForm,
)
from .market import EXCHANGE_FEE, SERVICES, get_market, get_service
from .news import ensure_news
from .push import broadcast_push
from .models import (
    SECTOR_CHOICES,
    AgentRating,
    ChatMessage,
    ChatThread,
    CivicRequest,
    DeviceLogin,
    FareTicket,
    Feedback,
    NewsComment,
    NewsItem,
    Notification,
    Profile,
    TaxBill,
    Transaction,
    Traveler,
    WeatherAlert,
    ensure_profile,
)
from .transit import (
    ROUTES_BY_ID,
    VILLAGES,
    WELCOME_BONUS,
    fare_for,
    timetable,
    ticket_allowed_epochs,
)
from .weather import (
    CONDITION_ICONS,
    current_conditions,
    ensure_alerts,
    forecast,
    sector_conditions,
    simulate_alert,
    today_alert,
)

TRX_QUANTUM = Decimal('0.000001')

SECTOR_INFO = {
    'aurelia': {
        'name': 'Aurelia Basin',
        'blurb': 'Warm shallow seas and floating forests. The first landing site.',
        'stat': 'Water 29°C',
    },
    'vermilion': {
        'name': 'Vermilion Steps',
        'blurb': 'Iron-red canyon country, dry and climbable at dawn.',
        'stat': 'Canyon depth 4 km',
    },
    'glasslands': {
        'name': 'The Glass Tundra',
        'blurb': 'Frozen plains that ring like struck crystal at dusk.',
        'stat': 'Low −40°C',
    },
    'pelagos': {
        'name': 'Pelagos Deep',
        'blurb': 'A midnight ocean lit from below by living light.',
        'stat': 'Depth 11 km',
    },
}


def home(request):
    return render(request, 'terra/home.html')


@require_http_methods(['GET', 'POST'])
def signup(request):
    if request.user.is_authenticated:
        return redirect('terra:dashboard')

    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Passenger record, funded with the 10,000 TRX welcome bonus.
            profile = ensure_profile(user)
            login(request, user)
            messages.success(
                request,
                _('Passage confirmed — you fly as %(callsign)s. '
                  'Welcome bonus: +%(bonus)s TRX is in your wallet.') % {
                      'callsign': profile.callsign,
                      'bonus': WELCOME_BONUS,
                  },
            )
            return redirect('terra:dashboard')
    else:
        form = SignupForm()

    return render(request, 'terra/signup.html', {'form': form})


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return redirect('terra:dashboard')

    next_url = request.GET.get('next', '')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, _('Airlock sealed. Mission Control is yours.'))
            return redirect(request.POST.get('next') or 'terra:dashboard')
    else:
        form = LoginForm(request)

    return render(request, 'terra/login.html', {'form': form, 'next': next_url})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, _('Signed out. The hatch is sealed behind you.'))
    return redirect('terra:home')


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    profile = ensure_profile(request.user)

    if request.method == 'POST':
        profile.tagline = request.POST.get('tagline', '').strip()[:140]
        profile.save(update_fields=['tagline'])
        messages.success(request, _('Log entry updated.'))
        return redirect('terra:dashboard')

    crew = User.objects.filter(is_active=True).select_related(
        'profile',
    ).order_by('-date_joined')[:5]

    return render(request, 'terra/dashboard.html', {
        'profile': profile,
        'sector_info': SECTOR_INFO.get(profile.sector),
        'crew': crew,
    })


# ---------------- TerraX market ----------------

def market(request):
    """Public market page; wallet + trading for signed-in passengers."""
    quotes = get_market()
    context = {'market': quotes, 'services': SERVICES}
    if request.user.is_authenticated:
        profile = ensure_profile(request.user)
        context.update({
            'profile': profile,
            'sectors': SECTOR_CHOICES,
            'transactions': request.user.transactions.all()[:15],
        })
    return render(request, 'terra/market.html', context)


def _first_error(form):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return None


@login_required
@require_POST
def trade(request):
    """Buy TerraX with Earth credits, or sell it back."""
    price = get_market()['trx_price']
    action = request.POST.get('action', '')
    profile = ensure_profile(request.user)

    if action == 'buy':
        form = BuyForm(request.POST)
        if not form.is_valid():
            messages.error(request, _first_error(form) or _('Invalid amount.'))
            return redirect('terra:market')
        usd = form.cleaned_data['amount']
        trx_got = ((usd * (Decimal('1') - EXCHANGE_FEE)) / price).quantize(TRX_QUANTUM)
        with transaction.atomic():
            profile.refresh_from_db()
            if profile.usd_balance < usd:
                messages.error(
                    request,
                    _('Not enough Earth credits — your wallet holds '
                      '$%(balance)s.') % {'balance': f'{profile.usd_balance:,.2f}'},
                )
                return redirect('terra:market')
            profile.usd_balance -= usd
            profile.trx_balance += trx_got
            profile.save(update_fields=['usd_balance', 'trx_balance'])
            Transaction.objects.create(
                user=profile.user,
                kind='buy',
                trx=trx_got,
                usd=-usd,
                price_usd=price,
                note=f'Bought TRX at ${price:,.2f}',
            )
        messages.success(
            request,
            _('Filled: %(trx)s TRX for $%(usd)s.') % {
                'trx': trx_got,
                'usd': f'{usd:,.2f}',
            },
        )
        return redirect('terra:market')

    if action == 'sell':
        form = SellForm(request.POST)
        if not form.is_valid():
            messages.error(request, _first_error(form) or _('Invalid amount.'))
            return redirect('terra:market')
        trx_sold = form.cleaned_data['amount']
        usd_got = (trx_sold * price * (Decimal('1') - EXCHANGE_FEE)).quantize(
            Decimal('0.01'),
        )
        with transaction.atomic():
            profile.refresh_from_db()
            if profile.trx_balance < trx_sold:
                messages.error(
                    request,
                    _('Not enough TerraX — your wallet holds '
                      '%(balance)s TRX.') % {'balance': profile.trx_balance},
                )
                return redirect('terra:market')
            profile.trx_balance -= trx_sold
            profile.usd_balance += usd_got
            profile.save(update_fields=['trx_balance', 'usd_balance'])
            Transaction.objects.create(
                user=profile.user,
                kind='sell',
                trx=-trx_sold,
                usd=usd_got,
                price_usd=price,
                note=f'Sold TRX at ${price:,.2f}',
            )
        messages.success(
            request,
            _('Sold %(trx)s TRX for $%(usd)s.') % {
                'trx': trx_sold,
                'usd': f'{usd_got:,.2f}',
            },
        )
        return redirect('terra:market')

    messages.error(request, _('Unknown trade action.'))
    return redirect('terra:market')
@login_required
@require_POST
def buy_service(request):
    """Purchase a site service with TerraX and apply its effect."""
    service = get_service(request.POST.get('service', ''))
    if not service:
        messages.error(request, _('That service does not exist.'))
        return redirect('terra:market')

    sector = None
    callsign = None
    if service['input'] == 'sector':
        sector = request.POST.get('sector', '')
        if sector not in dict(SECTOR_CHOICES):
            messages.error(request, _('Choose a valid sector.'))
            return redirect('terra:market')
    elif service['input'] == 'callsign':
        callsign = request.POST.get('callsign', '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9][A-Z0-9-]{2,23}', callsign):
            messages.error(
                request,
                _('Callsigns are 3–24 characters: letters, digits and dashes.'),
            )
            return redirect('terra:market')

    price = service['price']
    market_price = get_market()['trx_price']

    try:
        with transaction.atomic():
            profile = ensure_profile(request.user)
            if service['slug'] == 'priority' and profile.priority:
                messages.error(
                    request,
                    _('Priority boarding is already active on your manifest.'),
                )
                return redirect('terra:market')
            if callsign and Profile.objects.filter(
                callsign__iexact=callsign,
            ).exists():
                messages.error(
                    request,
                    _('Callsign %(callsign)s is already in use.') % {
                        'callsign': callsign,
                    },
                )
                return redirect('terra:market')
            if profile.trx_balance < price:
                messages.error(
                    request,
                    _('Not enough TerraX — %(name)s costs '
                      '%(price)s TRX and your wallet holds '
                      '%(balance)s TRX.') % {
                          'name': service['name'],
                          'price': price,
                          'balance': profile.trx_balance,
                      },
                )
                return redirect('terra:market')

            profile.trx_balance -= price
            if sector:
                profile.sector = sector
            if callsign:
                profile.callsign = callsign
            if service['slug'] == 'priority':
                profile.priority = True
            profile.save()

            Transaction.objects.create(
                user=profile.user,
                kind='service',
                trx=-price,
                usd=Decimal('0.00'),
                price_usd=market_price,
                note=service['name'],
            )
    except IntegrityError:
        messages.error(
            request,
            _('That callsign was claimed by another passenger a moment ago.'),
        )
        return redirect('terra:market')

    messages.success(
        request,
        _('%(name)s purchased for %(price)s TRX.') % service,
    )
    return redirect('terra:market')


# ---------------- Terra Chat ----------------

def _is_agent(user):
    """Staff or an explicitly flagged Novarian agent."""
    if not user.is_authenticated:
        return False
    if user.is_staff:
        return True
    return Profile.objects.filter(user=user, is_agent=True).exists()


def _can_access(user, thread):
    return thread.user_id == user.id or _is_agent(user)


def _system(thread, body):
    return ChatMessage.objects.create(thread=thread, role='system', body=body)


def _apply_ai(thread, text):
    """Terra AI answers, and the conversation side effects happen here."""
    intent, reply = ai_respond(text, thread)

    if thread.status == 'resolved' and intent != 'confirm_resolved':
        thread.status = 'ai_handling'
        _system(thread, 'Signal reopened by the Novarian.')

    if intent == 'confirm_resolved' and thread.status != 'resolved':
        thread.status = 'resolved'
        _system(thread, 'Signal marked resolved.')
    elif intent == 'escalate' and thread.status != 'escalated':
        thread.status = 'escalated'
        _system(thread, 'Relayed to the Novarian agent network.')
    else:
        if intent == 'issue':
            thread.kind = 'issue'
        if thread.status == 'open':
            thread.status = 'ai_handling'

    ChatMessage.objects.create(thread=thread, role='ai', body=reply)
    thread.save()


@login_required
@require_http_methods(['GET', 'POST'])
def chat(request):
    """Terra Chat home: my signals + start a new one."""
    if request.method == 'POST':
        body = (request.POST.get('body') or '').strip()[:2000]
        if not body:
            messages.error(request, _('The channel is open — say something first.'))
            return redirect('terra:chat')
        subject = re.sub(r'\s+', ' ', body)
        if len(subject) > 57:
            subject = subject[:57] + '…'
        with transaction.atomic():
            thread = ChatThread.objects.create(
                user=request.user, subject=subject,
            )
            ChatMessage.objects.create(
                thread=thread, author=request.user, role='user', body=body,
            )
            _apply_ai(thread, body)
        return redirect('terra:chat_thread', thread_id=thread.id)

    threads = request.user.chat_threads.all()[:30]
    return render(request, 'terra/chat.html', {
        'mode': 'mine',
        'threads': threads,
        'active': None,
        'is_agent': _is_agent(request.user),
    })


@login_required
def chat_thread(request, thread_id):
    """One conversation: the owner and Novarian agents may read it."""
    thread = get_object_or_404(ChatThread, id=thread_id)
    if not _can_access(request.user, thread):
        raise Http404('No signal here.')

    threads = request.user.chat_threads.all()[:30]
    return render(request, 'terra/chat.html', {
        'mode': 'mine',
        'threads': threads,
        'active': thread,
        'is_agent': _is_agent(request.user),
        'is_owner': thread.user_id == request.user.id,
    })


@login_required
@require_POST
def chat_send(request, thread_id):
    """Append a message: Novarian text triggers Terra AI, agent text claims
    the thread."""
    thread = get_object_or_404(ChatThread, id=thread_id)
    if not _can_access(request.user, thread):
        raise Http404('No signal here.')

    body = (request.POST.get('body') or '').strip()[:2000]
    if not body:
        messages.error(request, _('Empty transmission — nothing was sent.'))
        return redirect('terra:chat_thread', thread_id=thread.id)

    is_agent_reply = thread.user_id != request.user.id
    with transaction.atomic():
        if is_agent_reply:
            ChatMessage.objects.create(
                thread=thread, author=request.user, role='agent', body=body,
            )
            if thread.assigned_agent_id is None:
                thread.assigned_agent = request.user
                name = request.user.get_full_name() or request.user.username
                _system(thread, f'Novarian agent {name} joined the thread.')
            if thread.status != 'resolved':
                thread.status = 'escalated'
        else:
            ChatMessage.objects.create(
                thread=thread, author=request.user, role='user', body=body,
            )
            _apply_ai(thread, body)
        thread.save()
    return redirect('terra:chat_thread', thread_id=thread.id)


@login_required
def chat_messages(request, thread_id):
    """Polling endpoint: new messages since ?after=<id> + live status."""
    thread = get_object_or_404(ChatThread, id=thread_id)
    if not _can_access(request.user, thread):
        raise Http404('No signal here.')

    try:
        after = int(request.GET.get('after', 0))
    except (TypeError, ValueError):
        after = 0

    fresh = thread.messages.filter(id__gt=after)
    return JsonResponse({
        'status': thread.status,
        'status_label': thread.get_status_display(),
        'messages': [
            {
                'id': m.id,
                'role': m.role,
                'name': m.display_name,
                'body': m.body,
                'time': m.created_at.strftime('%H:%M'),
            }
            for m in fresh
        ],
    })


@login_required
@require_POST
def chat_action(request, thread_id):
    """Resolve or escalate a signal."""
    thread = get_object_or_404(ChatThread, id=thread_id)
    if not _can_access(request.user, thread):
        raise Http404('No signal here.')

    action = request.POST.get('action')
    name = request.user.get_full_name() or request.user.username

    if action == 'resolve' and thread.status != 'resolved':
        with transaction.atomic():
            thread.status = 'resolved'
            _system(thread, f'Signal marked resolved by {name}.')
            thread.save()
    elif (
        action == 'escalate'
        and thread.user_id == request.user.id
        and thread.status != 'escalated'
    ):
        with transaction.atomic():
            thread.status = 'escalated'
            _system(thread, 'Relayed to the Novarian agent network.')
            _, reply = ai_respond('escalate', thread)
            ChatMessage.objects.create(thread=thread, role='ai', body=reply)
            thread.save()
    return redirect('terra:chat_thread', thread_id=thread.id)


@login_required
def chat_agent(request):
    """Agent desk: the queue of open/escalated signals."""
    if not _is_agent(request.user):
        raise PermissionDenied('Agent clearance required.')

    queue = ChatThread.objects.filter(
        Q(status__in=['escalated', 'open']) | Q(assigned_agent=request.user),
    ).select_related('user', 'assigned_agent')[:40]
    threads = request.user.chat_threads.all()[:30]
    return render(request, 'terra/chat.html', {
        'mode': 'agent',
        'queue': queue,
        'threads': threads,
        'active': None,
        'is_agent': True,
    })


# ---------------- Weather & map ----------------

def weather(request):
    """Current conditions, the heat simulation and notification controls."""
    ensure_alerts()
    profile = None
    if request.user.is_authenticated:
        profile = ensure_profile(request.user)
    return render(request, 'terra/weather.html', {
        'profile': profile,
        'current': current_conditions(),
        'sectors': sector_conditions(),
        'forecast': forecast(),
        'today': today_alert(),
        'alerts': WeatherAlert.objects.all(),
    })


# World-space beacon anchors for the 3D map (x west, z north; −1..1).
PIN_POS = {
    'vermilion': (0.06, -0.60),   # Namib / Kalahari
    'aurelia': (-0.16, 0.04),     # Congo basin
    'glasslands': (0.12, 0.58),   # Sahara
    'pelagos': (-0.57, -0.21),    # East African coast
}


def map_view(request):
    """The 3D terrain map of Terra Nova with live sector weather."""
    ensure_alerts()
    profile = None
    if request.user.is_authenticated:
        profile = ensure_profile(request.user)
    sectors = sector_conditions()
    payload = []
    for key, s in sectors.items():
        wx, wy = PIN_POS.get(key, (0.0, 0.0))
        payload.append({
            **s,
            'wx': wx,
            'wy': wy,
            'mine': bool(profile and profile.sector == key),
        })
    return render(request, 'terra/map.html', {
        'sectors': sectors,
        'sectors_json': json.dumps(payload),
        'wx_icons': list(CONDITION_ICONS.values()),
        'current': current_conditions(),
        'profile': profile,
    })


def weather_status(request):
    """Polling endpoint: current conditions + unseen heat alerts."""
    ensure_alerts()
    try:
        after = int(request.GET.get('after', 0))
    except (TypeError, ValueError):
        after = 0

    alerts = [
        {
            'id': alert.id,
            'day': alert.day.isoformat(),
            'severity': alert.severity,
            'temp': float(alert.temp_c),
            'anomaly': float(alert.anomaly),
            'headline': alert.headline,
            'message': alert.message,
        }
        for alert in WeatherAlert.objects.filter(id__gt=after)
    ]
    return JsonResponse({
        'now': current_conditions(),
        'sectors': list(sector_conditions().values()),
        'alerts': alerts,
        'alert_total': WeatherAlert.objects.count(),
    })


@require_POST
def weather_trigger(request):
    """Fire the heat simulation immediately (demo button)."""
    ensure_alerts()
    data = simulate_alert()
    # Fan the same alert out as a real web push — subscribers see it
    # through the service worker even with this tab closed.
    data['push_sent'] = broadcast_push(
        title=data['headline'],
        message=data['message'],
        url='/weather/',
        tag=f"terra-sim-{data['id']}",
    )
    return JsonResponse(data)


# ---------------- Government portal ----------------

def _civic_profile(user):
    return ensure_profile(user)


@login_required
def government(request):
    """The Novarian government portal: tax, roads, records, pension, waste."""
    profile = _civic_profile(request.user)
    bill, _created = get_or_create_tax_bill(profile)
    age, eligible, months_left = pension_state(profile)
    sector_names = dict(SECTOR_CHOICES)

    return render(request, 'terra/government.html', {
        'profile': profile,
        'bill': bill,
        'fiscal': fiscal_code(),
        'tax_schedule': [
            (code, sector_names.get(code, code), amount)
            for code, amount in TAX_SCHEDULE.items()
        ],
        'paid_bills': request.user.tax_bills.filter(status='paid')[:8],
        'requests': request.user.civic_requests.filter(
            category__in=['road', 'waste'],
        )[:10],
        'waste': waste_schedule(profile.sector),
        'ss': social_security(request.user),
        'age': age,
        'eligible': eligible,
        'months_left': months_left,
        'claimed_this_month': months_since_claim(request.user),
        'pension_monthly': PENSION_MONTHLY,
        'sector_names': sector_names,
        'today': timezone.localdate().isoformat(),
    })


@login_required
@require_POST
def tax_pay(request):
    """Settle the current fiscal levy in TerraX."""
    profile = _civic_profile(request.user)
    bill, _created = get_or_create_tax_bill(profile)

    if bill.status == 'paid':
        messages.info(
            request,
            _('%(code)s is already settled.') % {'code': bill.code},
        )
        return redirect('terra:government')

    price = get_market()['trx_price']
    with transaction.atomic():
        profile.refresh_from_db()
        if profile.trx_balance < bill.amount_trx:
            messages.error(
                request,
                _('Not enough TerraX — the %(code)s levy is '
                  '%(amount)s TRX and your wallet holds '
                  '%(balance)s TRX.') % {
                      'code': bill.code,
                      'amount': bill.amount_trx,
                      'balance': profile.trx_balance,
                  },
            )
            return redirect('terra:government')
        profile.trx_balance -= bill.amount_trx
        profile.save(update_fields=['trx_balance'])
        bill.status = 'paid'
        bill.paid_at = timezone.now()
        bill.save(update_fields=['status', 'paid_at'])
        Transaction.objects.create(
            user=request.user,
            kind='tax',
            trx=-bill.amount_trx,
            usd=Decimal('0.00'),
            price_usd=price,
            note=f'{bill.code} civic levy',
        )
    messages.success(
        request,
        _('%(code)s settled — %(amount)s TRX paid. '
          'The receipt is in your TerraX ledger.') % {
              'code': bill.code,
              'amount': bill.amount_trx,
          },
    )
    return redirect('terra:government')


@login_required
@require_POST
def pension_claim(request):
    """Claim the monthly elder pension (age 65+, once per calendar month)."""
    profile = _civic_profile(request.user)
    age, eligible, months_left = pension_state(profile)

    if age is None:
        messages.error(
            request,
            _('No date of birth on file — register it at the pension desk first.'),
        )
        return redirect('terra:government')
    if not eligible:
        messages.error(
            request,
            _('Eligibility starts at age %(age)s — '
              'you are %(months)s months away.') % {
                  'age': PENSION_AGE,
                  'months': months_left,
              },
        )
        return redirect('terra:government')
    if months_since_claim(request.user):
        messages.info(request, _('This month’s pension is already on your ledger.'))
        return redirect('terra:government')

    price = get_market()['trx_price']
    with transaction.atomic():
        profile.refresh_from_db()
        profile.trx_balance += PENSION_MONTHLY
        profile.save(update_fields=['trx_balance'])
        Transaction.objects.create(
            user=request.user,
            kind='pension',
            trx=PENSION_MONTHLY,
            usd=Decimal('0.00'),
            price_usd=price,
            note=f'Elder pension · {timezone.localdate():%b %Y}',
        )
    messages.success(
        request,
        _('Pension claimed — %(amount)s TRX credited. '
          'Next claim opens next month.') % {'amount': PENSION_MONTHLY},
    )
    return redirect('terra:government')


@login_required
@require_POST
def civic_profile(request):
    """File a date of birth (pension desk)."""
    raw = (request.POST.get('date_of_birth') or '').strip()
    try:
        dob = date.fromisoformat(raw)
    except ValueError:
        messages.error(request, _('Enter a valid date of birth (YYYY-MM-DD).'))
        return redirect('terra:government')

    today = timezone.localdate()
    if dob > today:
        messages.error(request, _('Date of birth cannot be in the future.'))
        return redirect('terra:government')
    age = age_on(dob)
    if age > 120:
        messages.error(request, _('That age cannot be right — check the date.'))
        return redirect('terra:government')

    profile = _civic_profile(request.user)
    profile.date_of_birth = dob
    profile.save(update_fields=['date_of_birth'])
    messages.success(
        request,
        _('Date of birth on file — age %(age)s. The pension desk is updated.') % {
            'age': age,
        },
    )
    return redirect('terra:government')


@login_required
@require_POST
def civic_request(request):
    """File a road, waste or medical service request."""
    category = request.POST.get('category')
    if category not in dict(CivicRequest.CATEGORY_CHOICES):
        messages.error(request, _('Unknown request type.'))
        return redirect('terra:government')

    sector = request.POST.get('sector')
    if sector not in dict(SECTOR_CHOICES):
        messages.error(request, _('Choose a valid sector.'))
        return redirect('terra:government')

    location = (request.POST.get('location') or '').strip()[:140]
    if len(location) < 3:
        messages.error(request, _('Give the location at least a few characters.'))
        return redirect('terra:government')

    detail = (request.POST.get('detail') or '').strip()[:600]
    civic = CivicRequest.objects.create(
        user=request.user,
        category=category,
        sector=sector,
        location=location,
        detail=detail,
    )
    label = dict(CivicRequest.CATEGORY_CHOICES)[category]
    messages.success(
        request,
        _('%(label)s request filed · tracking %(tracking)s. '
          'Watch it move through review below.') % {
              'label': label,
              'tracking': civic.tracking,
          },
    )
    next_view = request.POST.get('next')
    if next_view in ('government', 'health'):
        return redirect(f'terra:{next_view}')
    return redirect('terra:government')


@login_required
def health(request):
    """Health portal: Terra Watch, medical requests, nearest facilities."""
    profile = _civic_profile(request.user)
    return render(request, 'terra/health.html', {
        'profile': profile,
        'watch_price': TERRA_WATCH_PRICE,
        'device': device_id(request.user),
        'vitals': vitals(request.user) if profile.terra_watch else None,
        'facilities': facilities_for(request.user),
        'medical_requests': request.user.civic_requests.filter(
            category='medical',
        )[:8],
        'sector_names': dict(SECTOR_CHOICES),
    })


@login_required
@require_POST
def terra_watch(request):
    """Pair the Terra Watch health monitor for 50 TRX."""
    profile = _civic_profile(request.user)
    if profile.terra_watch:
        messages.info(
            request,
            _('Terra Watch %(device)s is already paired.') % {
                'device': device_id(request.user),
            },
        )
        return redirect('terra:health')

    price = get_market()['trx_price']
    with transaction.atomic():
        profile.refresh_from_db()
        if profile.trx_balance < TERRA_WATCH_PRICE:
            messages.error(
                request,
                _('Not enough TerraX — the Terra Watch costs '
                  '%(price)s TRX and your wallet holds '
                  '%(balance)s TRX.') % {
                      'price': TERRA_WATCH_PRICE,
                      'balance': profile.trx_balance,
                  },
            )
            return redirect('terra:health')
        profile.trx_balance -= TERRA_WATCH_PRICE
        profile.terra_watch = True
        profile.save(update_fields=['trx_balance', 'terra_watch'])
        Transaction.objects.create(
            user=request.user,
            kind='service',
            trx=-TERRA_WATCH_PRICE,
            usd=Decimal('0.00'),
            price_usd=price,
            note='Terra Watch device',
        )
    messages.success(
        request,
        _('Terra Watch paired · device %(device)s '
          'is streaming vitals.') % {'device': device_id(request.user)},
    )
    return redirect('terra:health')


# ---------------- Transport ----------------

def _self_traveler(user):
    """Every account travels as themselves — created on first visit."""
    traveler, _created = Traveler.objects.get_or_create(
        user=user,
        relation='self',
        defaults={'name': user.get_full_name() or user.username},
    )
    return traveler


def _pay_fare(request, profile):
    """Validate the selection, debit the wallet and issue a QR ticket."""
    selection = (request.POST.get('depart') or '').strip()
    try:
        route_id, epoch_raw = selection.split('|', 1)
        epoch = int(epoch_raw)
    except ValueError:
        messages.error(request, _('Choose a departure from the board first.'))
        return redirect('terra:transport')

    route = ROUTES_BY_ID.get(route_id)
    if route is None or epoch not in ticket_allowed_epochs(route):
        messages.error(request, _('That departure has already left the station.'))
        return redirect('terra:transport')

    try:
        traveler_id = int(request.POST.get('traveler_id', ''))
    except ValueError:
        traveler_id = 0
    traveler = Traveler.objects.filter(
        id=traveler_id, user=request.user,
    ).first()
    if traveler is None:
        messages.error(request, _('Choose who is travelling first.'))
        return redirect('terra:transport')

    fare = fare_for(route, traveler)
    departure = datetime.fromtimestamp(
        epoch, tz=timezone.get_current_timezone(),
    )
    price = get_market()['trx_price']

    with transaction.atomic():
        profile.refresh_from_db()
        if profile.trx_balance < fare:
            messages.error(
                request,
                _('Not enough TerraX — this fare is %(fare)s TRX and your '
                  'wallet holds %(balance)s TRX.') % {
                      'fare': fare,
                      'balance': profile.trx_balance,
                  },
            )
            return redirect('terra:transport')
        balance_before = profile.trx_balance
        profile.trx_balance -= fare
        profile.save(update_fields=['trx_balance'])
        ticket = FareTicket.objects.create(
            user=request.user,
            traveler=traveler,
            route_id=route['id'],
            route_name=route['name'],
            kind=route['kind'],
            destination=route['destination'],
            departure=departure,
            fare_trx=fare,
            code=secrets.token_hex(8),
        )
        Transaction.objects.create(
            user=request.user,
            kind='fare',
            trx=-fare,
            usd=Decimal('0.00'),
            price_usd=price,
            note=f"{route['id']} {route['name']} · {traveler.name}",
        )

    messages.success(
        request,
        _('Fare paid — %(before)s − %(fare)s = %(balance)s TRX. '
          'QR ticket issued for %(route)s at %(time)s, ready for the '
          'receiver.') % {
              'before': balance_before,
              'fare': fare,
              'balance': profile.trx_balance,
              'route': route['id'],
              'time': f'{departure:%H:%M}',
          },
    )
    return redirect('terra:transport')


@login_required
@require_http_methods(['GET', 'POST'])
def transport(request):
    """Departure board, fare payment and QR tickets for Novarians."""
    profile = _civic_profile(request.user)
    _self_traveler(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'pay':
            return _pay_fare(request, profile)

        if action == 'add_traveler':
            name = (request.POST.get('name') or '').strip()[:60]
            relation = request.POST.get('relation')
            relations = dict(Traveler.RELATION_CHOICES)
            if len(name) < 2:
                messages.error(request, _('Give the traveller a name.'))
            elif relation not in relations:
                messages.error(request, _('Choose a relationship.'))
            else:
                Traveler.objects.create(
                    user=request.user, name=name, relation=relation,
                )
                messages.success(
                    request,
                    _('%(name)s added — you can now buy their fare too.') % {
                        'name': name,
                    },
                )
            return redirect('terra:transport')

        if action == 'scan':
            try:
                ticket = FareTicket.objects.get(
                    id=int(request.POST.get('ticket_id', '')),
                    user=request.user,
                )
            except (ValueError, FareTicket.DoesNotExist):
                messages.error(request, _('That ticket is not on your account.'))
                return redirect('terra:transport')
            if ticket.used:
                messages.info(request, _('This ticket was already scanned.'))
            else:
                ticket.used = True
                ticket.save(update_fields=['used'])
                messages.success(
                    request,
                    _('Receiver accepted %(route)s · %(who)s is aboard. '
                      'Safe travels.') % {
                          'route': ticket.route_id,
                          'who': ticket.traveler.name,
                      },
                )
            return redirect('terra:transport')

        messages.error(request, _('Unknown transport action.'))
        return redirect('terra:transport')

    board = timetable(profile.sector)
    return render(request, 'terra/transport.html', {
        'profile': profile,
        'village': VILLAGES.get(profile.sector, profile.sector_name),
        'board': board,
        'first_fare': board[0]['fare'] if board else Decimal('0'),
        'first_result': (
            profile.trx_balance - board[0]['fare'] if board
            else profile.trx_balance
        ),
        'travelers': request.user.travelers.all(),
        'tickets': request.user.tickets.select_related('traveler')[:8],
        'bonus': request.user.transactions.filter(kind='bonus').first(),
    })


# ---------------- News section ----------------

def news(request):
    """The newsroom: featured lead story plus the archive, filterable."""
    ensure_news()
    category = request.GET.get('category', '')
    items = NewsItem.objects.all()
    active = ''
    if category in dict(NewsItem.CATEGORY_CHOICES):
        items = items.filter(category=category)
        active = category

    lead = next((item for item in items if item.is_featured), None)
    stream = [item for item in items if item is not lead]
    return render(request, 'terra/news.html', {
        'lead': lead,
        'stream': stream,
        'categories': [
            (code, label, NewsItem.objects.filter(category=code).count())
            for code, label in NewsItem.CATEGORY_CHOICES
        ],
        'active': active,
        'total': NewsItem.objects.count(),
    })


def news_detail(request, slug):
    """A single dispatch, with the rest of its category beneath it."""
    ensure_news()
    item = get_object_or_404(NewsItem, slug=slug)
    related = NewsItem.objects.filter(category=item.category).exclude(pk=item.pk)[:3]
    return render(request, 'terra/news_detail.html', {
        'item': item,
        'related': related,
        'paragraphs': [p.strip() for p in item.body.split('\n\n') if p.strip()],
        'comments': item.comments.select_related('user'),
    })


@login_required
@require_POST
def news_comment(request, slug):
    """Post a reader comment under a dispatch."""
    ensure_news()
    item = get_object_or_404(NewsItem, slug=slug)
    body = (request.POST.get('body') or '').strip()[:1000]
    if not body:
        messages.error(
            request,
            _('The comment is empty — write something first.'),
        )
    else:
        NewsComment.objects.create(item=item, user=request.user, body=body)
        messages.success(request, _('Comment posted.'))
    return redirect('terra:news_detail', slug=slug)


# ---------------- Feedback ----------------

def feedback(request):
    """The open channel: file an insight, read what other Novarians filed."""
    return render(request, 'terra/feedback.html', {
        'feedbacks': Feedback.objects.select_related('user'),
        'topics': Feedback.TOPIC_CHOICES,
    })


@login_required
@require_POST
def feedback_post(request):
    """File one insight from the Feedback page."""
    topic = request.POST.get('topic', 'idea')
    body = (request.POST.get('body') or '').strip()[:1000]
    valid_topics = {code for code, _label in Feedback.TOPIC_CHOICES}
    if topic not in valid_topics:
        topic = 'idea'
    if not body:
        messages.error(
            request,
            _('The insight is empty — write something first.'),
        )
    else:
        Feedback.objects.create(user=request.user, topic=topic, body=body)
        messages.success(
            request,
            _('Insight filed — the council reads every signal.'),
        )
    return redirect('terra:feedback')


# ---------------- Notification centre ----------------

@login_required
@require_http_methods(['GET', 'POST'])
def notifications(request):
    """The passenger-facing notification centre (security + device alerts)."""
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'mark_all':
            updated = request.user.notifications.filter(is_read=False).update(
                is_read=True,
            )
            messages.success(
                request,
                ngettext(
                    '%(n)s signal acknowledged.',
                    '%(n)s signals acknowledged.',
                    updated,
                ) % {'n': updated},
            )
        elif action == 'mark' and request.POST.get('id'):
            request.user.notifications.filter(
                id=request.POST['id'],
            ).update(is_read=True)
            messages.success(request, _('Signal acknowledged.'))
        elif action == 'sign_out_elsewhere':
            # Revoke every other session for this user (keep the current one).
            from django.contrib.sessions.models import Session

            current = request.session.session_key
            revoked = 0
            for session in Session.objects.filter(
                expire_date__gte=timezone.now(),
            ):
                data = session.get_decoded()
                if data.get('_auth_user_id') == str(request.user.pk):
                    if session.session_key != current:
                        session.delete()
                        revoked += 1
            messages.success(
                request,
                ngettext(
                    '%(n)s other session sealed behind you.',
                    '%(n)s other sessions sealed behind you.',
                    revoked,
                ) % {'n': revoked},
            )
        else:
            messages.error(request, _('Unknown signal action.'))
        return redirect('terra:notifications')

    alert_count = request.user.notifications.filter(is_read=False).count()
    return render(request, 'terra/notifications.html', {
        'notifications': request.user.notifications.all()[:40],
        'alert_count': alert_count,
        'devices': request.user.devices.all(),
        'active_limit': 2,
    })


# ---------------- Account centre ----------------

def _rateable_agents(user):
    """Agents this passenger can rate: conversed-with, then all agents."""
    talked_with = set(
        ChatThread.objects.filter(user=user)
        .exclude(assigned_agent__isnull=True)
        .values_list('assigned_agent_id', flat=True)
    )
    agents = list(
        User.objects.filter(
            Q(chat_assigned__user=user) | Q(profile__is_agent=True),
            is_active=True,
        )
        .select_related('profile')
        .distinct()
        .order_by('username')
    )
    given = {
        r.agent_id: r
        for r in user.agent_ratings_given.all()
    }
    return [
        {
            'user': agent,
            'rating': given.get(agent.pk),
            'met': agent.pk in talked_with,
        }
        for agent in agents
    ]


@login_required
@require_http_methods(['GET', 'POST'])
def account(request):
    """The account centre: profile, photo, dossier, agent ratings."""
    profile = ensure_profile(request.user)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'profile':
            form = AccountForm(request.POST, user=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, _('Passenger record updated.'))
            else:
                messages.error(
                    request,
                    _first_error(form) or _('Could not save the record.'),
                )
            return redirect('terra:account')

        if action == 'avatar':
            avatar_form = AvatarForm(request.POST, request.FILES)
            if avatar_form.is_valid():
                if profile.avatar:
                    profile.avatar.delete(save=False)
                profile.avatar = avatar_form.cleaned_data['avatar']
                profile.save(update_fields=['avatar'])
                messages.success(request, _('Passenger photo updated.'))
            else:
                messages.error(
                    request,
                    _first_error(avatar_form) or _('Could not store the photo.'),
                )
            return redirect('terra:account')

        if action == 'avatar_clear':
            if profile.avatar:
                profile.avatar.delete(save=False)
                profile.avatar = ''
                profile.save(update_fields=['avatar'])
                messages.info(request, _('Passenger photo removed.'))
            return redirect('terra:account')

        if action == 'rate':
            rating_form = RatingForm(request.POST)
            if rating_form.is_valid():
                agent = User.objects.get(
                    pk=rating_form.cleaned_data['agent'],
                )
                AgentRating.objects.update_or_create(
                    user=request.user,
                    agent=agent,
                    defaults={
                        'rating': rating_form.cleaned_data['rating'],
                        'comment': rating_form.cleaned_data['comment'],
                    },
                )
                messages.success(
                    request,
                    _('Rating saved — %(stars)s★ for %(who)s.') % {
                        'stars': rating_form.cleaned_data['rating'],
                        'who': agent.username,
                    },
                )
            else:
                messages.error(
                    request,
                    _first_error(rating_form) or _('Could not save the rating.'),
                )
            return redirect('terra:account')

        messages.error(request, _('Unknown account action.'))
        return redirect('terra:account')

    return render(request, 'terra/account.html', {
        'profile': profile,
        'account_form': AccountForm(user=request.user),
        'avatar_form': AvatarForm(),
        'rateable': _rateable_agents(request.user),
    })


@login_required
def account_pdf(request):
    """Download the full passenger dossier as a PDF."""
    from .dossier import build_dossier

    data = build_dossier(request.user)
    filename = f'TerraNova-Dossier-{request.user.username}.pdf'
    response = HttpResponse(data, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# CIVIC_VIEWS
