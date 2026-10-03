import random

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import LoginForm, SignupForm
from .models import SECTOR_CHOICES, Profile

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
            Profile.objects.create(
                user=user,
                sector=random.choice([code for code, _ in SECTOR_CHOICES]),
            )
            login(request, user)
            messages.success(
                request,
                f'Passage confirmed. Welcome aboard, '
                f'{user.first_name or user.username} — you fly as '
                f'{user.profile.callsign}.',
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
            messages.success(request, 'Airlock sealed. Mission Control is yours.')
            return redirect(request.POST.get('next') or 'terra:dashboard')
    else:
        form = LoginForm(request)

    return render(request, 'terra/login.html', {'form': form, 'next': next_url})


@require_POST
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, 'Signed out. The hatch is sealed behind you.')
    return redirect('terra:home')


@login_required
@require_http_methods(['GET', 'POST'])
def dashboard(request):
    profile, _ = Profile.objects.get_or_create(
        user=request.user,
        defaults={'sector': random.choice([code for code, _ in SECTOR_CHOICES])},
    )

    if request.method == 'POST':
        profile.tagline = request.POST.get('tagline', '').strip()[:140]
        profile.save(update_fields=['tagline'])
        messages.success(request, 'Log entry updated.')
        return redirect('terra:dashboard')

    crew = User.objects.filter(is_active=True).order_by('-date_joined')[:5]

    return render(request, 'terra/dashboard.html', {
        'profile': profile,
        'sector_info': SECTOR_INFO.get(profile.sector),
        'crew': crew,
    })
