import importlib
import json
import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation

from .models import (
    AgentRating,
    ChatThread,
    CivicRequest,
    DeviceLogin,
    FareTicket,
    Feedback,
    LoginAttempt,
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


class HomeTests(TestCase):
    def test_home_renders(self):
        response = self.client.get(reverse('terra:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Terra Nova')


class SignupTests(TestCase):
    def test_signup_creates_user_profile_and_logs_in(self):
        response = self.client.post(reverse('terra:signup'), {
            'username': 'voyager',
            'email': 'voyager@example.com',
            'first_name': 'Voyager One',
            'password1': 'lunar-tide-42x',
            'password2': 'lunar-tide-42x',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('terra:dashboard'))
        user = User.objects.get(username='voyager')
        self.assertEqual(user.email, 'voyager@example.com')
        self.assertTrue(hasattr(user, 'profile'))
        self.assertTrue(user.profile.callsign)
        self.assertContains(response, 'Mission Control')

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user('other', 'other@example.com', 'pass12345x')
        response = self.client.post(reverse('terra:signup'), {
            'username': 'newbie',
            'email': 'other@example.com',
            'first_name': 'New Bee',
            'password1': 'lunar-tide-42x',
            'password2': 'lunar-tide-42x',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'A passenger already uses that email address.')
        self.assertFalse(User.objects.filter(username='newbie').exists())


class WelcomeBonusTests(TestCase):
    """Every account holds 10,000 TRX — signup, admin deck, shell or backfill."""

    def test_ensure_profile_funds_wallet_exactly_once(self):
        user = User.objects.create_user(
            'drifter', 'drifter@example.com', 'pw-lunar-77x',
        )
        profile = ensure_profile(user)
        self.assertTrue(profile.callsign)
        self.assertEqual(profile.trx_balance, Decimal('10000.000000'))
        bonus = Transaction.objects.get(user=user, kind='bonus')
        self.assertEqual(bonus.trx, Decimal('10000.000000'))
        self.assertIn('Welcome bonus', bonus.note)

        again = ensure_profile(user)
        self.assertEqual(again.pk, profile.pk)
        profile.refresh_from_db()
        self.assertEqual(profile.trx_balance, Decimal('10000.000000'))
        self.assertEqual(Transaction.objects.filter(user=user).count(), 1)

    def test_first_dashboard_visit_funds_profileless_account(self):
        """Accounts created outside signup (admin/shell) get funded too."""
        self.client.force_login(
            User.objects.create_user(
                'superlee', 'superlee@example.com', 'pw-lunar-77x',
            ),
        )
        response = self.client.get(reverse('terra:dashboard'))
        self.assertEqual(response.status_code, 200)

        profile = Profile.objects.get(user__username='superlee')
        self.assertEqual(profile.trx_balance, Decimal('10000.000000'))
        self.assertTrue(
            Transaction.objects.filter(
                user=profile.user, kind='bonus',
            ).exists(),
        )

    def test_backfill_funds_legacy_zero_wallets_only(self):
        legacy = User.objects.create_user(
            'legacy', 'legacy@example.com', 'pw-lunar-77x',
        )
        Profile.objects.create(user=legacy)          # born before the bonus
        spender = User.objects.create_user(
            'spender', 'spender@example.com', 'pw-lunar-77x',
        )
        Profile.objects.create(
            user=spender, trx_balance=Decimal('0.000000'),
        )
        Transaction.objects.create(
            user=spender, kind='fare', trx=Decimal('-5.000000'),
            usd=Decimal('0.00'), price_usd=Decimal('0.00'),
        )
        funded = User.objects.create_user(
            'funded', 'funded@example.com', 'pw-lunar-77x',
        )
        Profile.objects.create(
            user=funded, trx_balance=Decimal('42.000000'),
        )

        module = importlib.import_module(
            'terra.migrations.0009_backfill_welcome_bonus',
        )
        module.grant_welcome_bonus(apps, None)

        legacy_profile = Profile.objects.get(user=legacy)
        self.assertEqual(legacy_profile.trx_balance, Decimal('10000.000000'))
        self.assertTrue(
            Transaction.objects.filter(user=legacy, kind='bonus').exists(),
        )
        # a zero wallet with history is a real balance — left alone
        spender_profile = Profile.objects.get(user=spender)
        self.assertEqual(spender_profile.trx_balance, Decimal('0.000000'))
        self.assertFalse(
            Transaction.objects.filter(user=spender, kind='bonus').exists(),
        )
        # a funded wallet is untouched
        funded_profile = Profile.objects.get(user=funded)
        self.assertEqual(funded_profile.trx_balance, Decimal('42.000000'))
        self.assertFalse(
            Transaction.objects.filter(user=funded).exists(),
        )


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'pilot', 'pilot@example.com', 'secure-pass-99x',
        )

    def test_login_and_logout(self):
        response = self.client.post(reverse('terra:login'), {
            'username': 'pilot',
            'password': 'secure-pass-99x',
        })
        self.assertRedirects(response, reverse('terra:dashboard'))

        response = self.client.get(reverse('terra:dashboard'))
        self.assertContains(response, 'pilot')

        response = self.client.post(reverse('terra:logout'))
        self.assertRedirects(response, reverse('terra:home'))

        response = self.client.get(reverse('terra:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_login_wrong_password(self):
        response = self.client.post(reverse('terra:login'), {
            'username': 'pilot',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter a correct username and password.')


class NavTests(TestCase):
    """Compact, mobile-ready navigation (hamburger + slide-down panel)."""

    def test_nav_is_compact_and_mobile_ready(self):
        response = self.client.get(reverse('terra:home'))
        self.assertEqual(response.status_code, 200)
        # Hamburger toggle and a single panel holding links + account controls.
        self.assertContains(response, 'class="nav__menu" data-nav-menu')
        self.assertContains(response, 'data-menu-toggle')
        self.assertContains(response, 'aria-expanded="false"')
        # Section links and account controls live inside the panel.
        self.assertContains(response, 'data-nav-links')
        self.assertContains(response, 'nav__lang')

    def test_auth_controls_visible_for_guest(self):
        response = self.client.get(reverse('terra:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('terra:signup'))


class TutorialTests(TestCase):
    """First-login tour overlay + dismiss endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            'rookie', 'rookie@example.com', 'orbit-pass-88',
        )

    def _login(self):
        self.client.login(username='rookie', password='orbit-pass-88')

    def test_tour_shown_on_first_login(self):
        self._login()
        response = self.client.get(reverse('terra:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-tutorial')
        self.assertContains(response, 'Welcome to Terra Nova')
        self.assertContains(response, 'First contact')
        self.assertContains(response, 'Mission Control')

    def test_tour_not_shown_to_anonymous(self):
        response = self.client.get(reverse('terra:home'))
        self.assertNotContains(response, 'data-tutorial')

    def test_dismiss_hides_tour(self):
        self._login()
        response = self.client.post(reverse('terra:tutorial_dismiss'))
        self.assertRedirects(response, reverse('terra:dashboard'))
        response = self.client.get(reverse('terra:dashboard'))
        self.assertNotContains(response, 'data-tutorial')

    def test_dismiss_requires_login(self):
        response = self.client.post(reverse('terra:tutorial_dismiss'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_dismiss_requires_post(self):
        self._login()
        response = self.client.get(reverse('terra:tutorial_dismiss'))
        self.assertEqual(response.status_code, 405)


class DashboardTests(TestCase):
    def test_requires_login(self):
        response = self.client.get(reverse('terra:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_creates_profile_on_first_visit_and_updates_tagline(self):
        self.client.force_login(
            User.objects.create_user('cadet', 'cadet@example.com', 'pass-word-77'),
        )
        response = self.client.get(reverse('terra:dashboard'))
        self.assertEqual(response.status_code, 200)
        profile = Profile.objects.get(user__username='cadet')
        self.assertTrue(profile.callsign)

        response = self.client.post(
            reverse('terra:dashboard'),
            {'tagline': 'Botanist. Prefers warm gravity.'},
        )
        self.assertRedirects(response, reverse('terra:dashboard'))
        profile.refresh_from_db()
        self.assertEqual(profile.tagline, 'Botanist. Prefers warm gravity.')


class PwaTests(TestCase):
    """Progressive web app endpoints, metadata and assets."""

    def test_manifest_serves_valid_json(self):
        response = self.client.get('/manifest.json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('json', response['Content-Type'])

        data = json.loads(response.content)
        self.assertEqual(data['name'], 'Terra Nova')
        self.assertEqual(data['start_url'], '/')
        self.assertEqual(data['scope'], '/')
        self.assertEqual(data['display'], 'standalone')
        self.assertEqual(data['theme_color'], '#04060b')
        self.assertEqual(data['background_color'], '#04060b')
        self.assertFalse(data['prefer_related_applications'])
        self.assertEqual(data['categories'], ['education', 'lifestyle'])

        sizes = {icon['sizes'] for icon in data['icons']}
        self.assertIn('192x192', sizes)
        self.assertIn('512x512', sizes)
        purposes = {icon.get('purpose') for icon in data['icons']}
        self.assertIn('maskable', purposes)

        shortcut_urls = {shortcut['url'] for shortcut in data['shortcuts']}
        self.assertEqual(
            shortcut_urls,
            {'/mission-control/', '/signup/', '/market/'},
        )

    def test_serviceworker_serves_javascript(self):
        response = self.client.get('/serviceworker.js')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response['Content-Type'])

        content = response.content.decode()
        self.assertIn('terra-precache-', content)
        self.assertIn('/offline/', content)
        self.assertIn("'install'", content)
        self.assertIn('staleWhileRevalidate', content)
        self.assertIn('networkFirstNavigation', content)

    def test_offline_page_renders(self):
        response = self.client.get('/offline/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'You are <em>offline</em>.')
        self.assertContains(response, 'SERVED BY THE TERRA NOVA SERVICE WORKER')

    def test_pages_include_pwa_meta_and_registration(self):
        for url in ['/', '/login/', '/signup/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            self.assertContains(response, 'rel="manifest"')
            self.assertContains(
                response,
                "navigator.serviceWorker.register('/serviceworker.js'",
            )
            self.assertContains(response, 'rel="apple-touch-icon"')
            self.assertContains(response, 'name="theme-color"')

    def test_install_button_and_script_present(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="install-app"')
        self.assertContains(response, 'data-label-installed')
        self.assertContains(response, 'data-label-ios')
        self.assertContains(response, 'js/install.js')
        js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'install.js').read_text()
        self.assertIn('beforeinstallprompt', js)

    def test_pwa_icons_exist_with_expected_sizes(self):
        from django.contrib.staticfiles import finders
        from PIL import Image

        expected = {
            'img/pwa/icon-192x192.png': (192, 192),
            'img/pwa/icon-512x512.png': (512, 512),
            'img/pwa/maskable-512x512.png': (512, 512),
            'img/pwa/apple-touch-icon-180x180.png': (180, 180),
        }
        for name, size in expected.items():
            path = finders.find(name)
            self.assertIsNotNone(path, f'missing icon: {name}')
            with Image.open(path) as img:
                self.assertEqual(img.size, size, name)


class AccessibilityTests(TestCase):
    """Accessibility panel, text-to-speech and low-vision text rendering."""

    A11Y_MARKERS = [
        'id="a11y-panel"',
        'role="dialog"',
        'aria-modal="true"',
        'data-a11y-open',
        'static/js/accessibility.js',
        'static/css/accessibility.css',
        "localStorage.getItem('terra-a11y')",
        'family=Lexend',
    ]

    PANEL_CONTROLS = [
        'data-a11y-key="textSize"',
        'data-a11y-toggle="contrast"',
        'data-a11y-toggle="reading"',
        'data-a11y-toggle="links"',
        'data-a11y-toggle="motion"',
        'data-tts="play"',
        'data-tts="pause"',
        'data-tts-rate',
        'data-a11y-reset',
        'aria-live="polite"',
    ]

    def test_pages_include_a11y_panel_and_assets(self):
        for url in ['/', '/login/', '/offline/']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
            for marker in self.A11Y_MARKERS:
                self.assertContains(response, marker, msg_prefix=f'{url}: {marker}')
            for marker in self.PANEL_CONTROLS:
                self.assertContains(response, marker, msg_prefix=f'{url}: {marker}')

    def test_static_assets_exist(self):
        from django.contrib.staticfiles import finders

        self.assertIsNotNone(finders.find('css/accessibility.css'))
        self.assertIsNotNone(finders.find('js/accessibility.js'))

    def test_low_vision_rendering_rules_present(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        css = Path(finders.find('css/accessibility.css')).read_text()
        self.assertIn('data-text-size="xlarge"', css)
        self.assertIn('data-contrast="high"', css)
        self.assertIn('prefers-contrast: more', css)
        self.assertIn("font-family: 'Lexend'", css)
        self.assertIn('data-motion="reduce"', css)

        js = Path(finders.find('js/accessibility.js')).read_text()
        self.assertIn('speechSynthesis', js)
        self.assertIn('SpeechSynthesisUtterance', js)
        self.assertIn('SpeechRecognition', js)
        self.assertIn('terra:a11y-change', js)

    def test_dictation_never_attached_to_password_fields(self):
        from pathlib import Path

        from django.contrib.staticfiles import finders

        js = Path(finders.find('js/accessibility.js')).read_text()
        self.assertIn("'password'", js)


class MarketTests(TestCase):
    """TerraX market: pegs, pricing, trading and services."""

    FALLBACK_BTC = Decimal('108450.00')
    TRX_PRICE = Decimal('135562.50')  # 1.25 x BTC

    def setUp(self):
        cache.clear()
        patcher = patch(
            'terra.market.fetch_earth_prices',
            side_effect=OSError('network unavailable'),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _login(self, username='trader'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'market-pass-42x',
        )
        Profile.objects.create(user=user)
        self.client.force_login(user)
        return user

    # ---- pricing ----

    def test_market_price_math(self):
        from terra.market import get_market

        quotes = get_market()
        self.assertEqual(quotes['btc'], self.FALLBACK_BTC)
        self.assertEqual(quotes['trx_price'], self.TRX_PRICE)
        self.assertEqual(quotes['trx_change'], Decimal('2.30'))  # 1.84 * 1.25
        self.assertEqual(quotes['btc_peg'], Decimal('1.25'))
        self.assertEqual(quotes['eth_peg'], Decimal('5'))
        self.assertEqual(quotes['source'], 'fallback')
        self.assertEqual(len(quotes['series']), 48)
        self.assertTrue(quotes['chart_line'].startswith('M '))
        self.assertTrue(quotes['chart_area'].endswith('Z'))

    def test_public_market_page_shows_pegs_and_comparison(self):
        response = self.client.get(reverse('terra:market'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '$135,562.50')   # 1.25 x BTC
        self.assertContains(response, '$108,450.00')   # Bitcoin fallback
        self.assertContains(response, '$4,182.50')     # Ethereum fallback
        self.assertContains(response, '1 TRX = 1.25 BTC')
        self.assertContains(response, '1 TRX = 5 ETH')
        self.assertContains(response, 'Sector transfer')
        self.assertContains(response, 'Priority boarding')
        self.assertContains(response, 'terrax/terrax.svg')
        # anonymous visitors get the wallet CTA, not the desk
        self.assertContains(response, 'Open a TerraX')
        self.assertNotContains(response, 'id="id_mkt_buy"')

    def test_member_market_page_shows_wallet_and_desk(self):
        self._login()
        response = self.client.get(reverse('terra:market'))
        self.assertContains(response, 'id="id_mkt_buy"')
        self.assertContains(response, 'id="id_mkt_sell"')
        self.assertContains(response, '5,000.00')
        self.assertContains(response, 'No trades yet')
    # ---- earth markets ----

    def test_market_tracks_eight_earth_coins(self):
        from terra.market import get_market

        quotes = get_market()
        symbols = [coin['symbol'] for coin in quotes['coins']]
        self.assertEqual(
            symbols,
            ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'LTC'],
        )

        by_symbol = {coin['symbol']: coin for coin in quotes['coins']}
        self.assertEqual(by_symbol['BTC']['price'], Decimal('108450.00'))
        self.assertEqual(by_symbol['SOL']['price'], Decimal('186.40'))
        self.assertEqual(by_symbol['DOGE']['price'], Decimal('0.1842'))
        # declared pegs for BTC/ETH, live multiple for the rest
        self.assertEqual(by_symbol['BTC']['buys'], Decimal('1.25'))
        self.assertEqual(by_symbol['ETH']['buys'], Decimal('5'))
        self.assertEqual(
            by_symbol['SOL']['buys'],
            self.TRX_PRICE / Decimal('186.40'),
        )
        self.assertGreater(by_symbol['BTC']['mcap'], Decimal('1e12'))

    def test_public_market_page_shows_earth_markets_table(self):
        response = self.client.get(reverse('terra:market'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Earth markets')
        self.assertContains(response, 'mkt-table--coins')
        self.assertContains(response, 'Market cap')
        self.assertContains(response, '1 TRX buys')
        for name in ['Solana', 'BNB', 'XRP', 'Dogecoin', 'Cardano', 'Litecoin']:
            self.assertContains(response, name)
        self.assertContains(response, '$0.1842')   # DOGE at 4dp
        self.assertContains(response, '$2.15T')    # BTC market cap
        self.assertContains(response, 'mkt-market__buys')

    # ---- trading ----

    def test_anonymous_trade_redirects_to_login(self):
        response = self.client.post(
            reverse('terra:trade'),
            {'action': 'buy', 'amount': '100'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_buy_updates_wallet_and_ledger(self):
        self._login()
        response = self.client.post(
            reverse('terra:trade'),
            {'action': 'buy', 'amount': '1000.00'},
            follow=True,
        )
        self.assertRedirects(response, reverse('terra:market'))

        profile = Profile.objects.get(user__username='trader')
        expected_trx = (
            (Decimal('1000.00') * Decimal('0.995')) / self.TRX_PRICE
        ).quantize(Decimal('0.000001'))
        self.assertEqual(profile.usd_balance, Decimal('4000.00'))
        self.assertEqual(profile.trx_balance, expected_trx)

        tx = Transaction.objects.get(user=profile.user)
        self.assertEqual(tx.kind, 'buy')
        self.assertEqual(tx.usd, Decimal('-1000.00'))
        self.assertEqual(tx.trx, expected_trx)
        self.assertEqual(tx.price_usd, self.TRX_PRICE)

        output = [str(m) for m in response.context['messages']]
        self.assertTrue(any('Filled' in m for m in output), output)

    def test_buy_rejects_insufficient_credits(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.usd_balance = Decimal('5.00')
        profile.save()

        self.client.post(
            reverse('terra:trade'),
            {'action': 'buy', 'amount': '100'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.usd_balance, Decimal('5.00'))
        self.assertEqual(profile.trx_balance, Decimal('0.000000'))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_buy_rejects_invalid_amount(self):
        self._login()
        self.client.post(
            reverse('terra:trade'),
            {'action': 'buy', 'amount': '-5'},
            follow=True,
        )
        profile = Profile.objects.get(user__username='trader')
        self.assertEqual(profile.usd_balance, Decimal('5000.00'))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_sell_pays_out_credits(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('2.000000')
        profile.save()

        self.client.post(
            reverse('terra:trade'),
            {'action': 'sell', 'amount': '1.5'},
            follow=True,
        )
        profile.refresh_from_db()
        payout = (
            Decimal('1.5') * self.TRX_PRICE * Decimal('0.995')
        ).quantize(Decimal('0.01'))
        self.assertEqual(profile.trx_balance, Decimal('0.500000'))
        self.assertEqual(profile.usd_balance, Decimal('5000.00') + payout)
        self.assertEqual(Transaction.objects.filter(kind='sell').count(), 1)

    def test_sell_rejects_more_than_owned(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('1.000000')
        profile.save()

        self.client.post(
            reverse('terra:trade'),
            {'action': 'sell', 'amount': '2'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.trx_balance, Decimal('1.000000'))
        self.assertEqual(profile.usd_balance, Decimal('5000.00'))
        self.assertEqual(Transaction.objects.count(), 0)
    # ---- services ----

    def test_service_callsign_rename(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('5.000000')
        profile.save()

        self.client.post(
            reverse('terra:service'),
            {'service': 'callsign', 'callsign': 'nova-77'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.callsign, 'NOVA-77')
        self.assertEqual(profile.trx_balance, Decimal('4.750000'))

        tx = Transaction.objects.get(user=user)
        self.assertEqual(tx.kind, 'service')
        self.assertEqual(tx.trx, Decimal('-0.250000'))
        self.assertEqual(tx.note, 'Callsign rename')

    def test_service_sector_transfer_applies(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('5.000000')
        profile.save()
        original_callsign = profile.callsign

        self.client.post(
            reverse('terra:service'),
            {'service': 'sector', 'sector': 'pelagos'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.sector, 'pelagos')
        self.assertEqual(profile.callsign, original_callsign)
        self.assertEqual(profile.trx_balance, Decimal('4.600000'))

    def test_service_priority_purchases_once(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('5.000000')
        profile.save()

        self.client.post(
            reverse('terra:service'),
            {'service': 'priority'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertTrue(profile.priority)
        self.assertEqual(profile.trx_balance, Decimal('3.000000'))

        # a second attempt must not charge again
        self.client.post(
            reverse('terra:service'),
            {'service': 'priority'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.trx_balance, Decimal('3.000000'))
        self.assertEqual(Transaction.objects.count(), 1)

    def test_service_blocked_without_funds(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.trx_balance, Decimal('0.000000'))

        self.client.post(
            reverse('terra:service'),
            {'service': 'sector', 'sector': 'vermilion'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertNotEqual(profile.sector, 'vermilion')
        self.assertEqual(Transaction.objects.count(), 0)

    def test_service_rejects_invalid_callsign_and_sector(self):
        user = self._login()
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('5.000000')
        profile.save()
        original = profile.callsign

        self.client.post(
            reverse('terra:service'),
            {'service': 'callsign', 'callsign': '!!bad!!'},
            follow=True,
        )
        self.client.post(
            reverse('terra:service'),
            {'service': 'sector', 'sector': 'atlantis'},
            follow=True,
        )
        profile.refresh_from_db()
        self.assertEqual(profile.callsign, original)
        self.assertEqual(profile.trx_balance, Decimal('5.000000'))
        self.assertEqual(Transaction.objects.count(), 0)

    def test_dashboard_shows_wallet(self):
        user = self._login(username='walletgazer')
        profile = Profile.objects.get(user=user)
        profile.trx_balance = Decimal('1.250000')
        profile.save()

        response = self.client.get(reverse('terra:dashboard'))
        self.assertContains(response, 'TerraX wallet')
        self.assertContains(response, '1.250000')
        self.assertContains(response, 'Open the market')


class ChatTests(TestCase):
    """Terra Chat: AI replies, signals, escalation and agent hand-off."""

    def _user(self, username, agent=False):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'chat-pass-77x',
        )
        Profile.objects.create(user=user, is_agent=agent)
        return user

    def _start(self, body):
        """Log in as a fresh Novarian and open a signal."""
        user = self._user('novarian')
        self.client.force_login(user)
        self.client.post(reverse('terra:chat'), {'body': body})
        return user, user.chat_threads.first()

    # ---- access ----

    def test_chat_requires_login(self):
        response = self.client.get(reverse('terra:chat'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_welcome_page_and_launcher_present(self):
        self._user('novarian')
        self.client.force_login(User.objects.get(username='novarian'))
        response = self.client.get(reverse('terra:chat'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'chat__welcome')
        self.assertContains(response, 'Terra AI on duty')
        self.assertContains(response, 'data-quick')

        home = self.client.get(reverse('terra:home'))
        self.assertContains(home, 'chat-fab')
        self.assertContains(home, 'Terra Chat')

    # ---- Terra AI ----

    def test_new_signal_gets_ai_reply(self):
        user, thread = self._start('hello there')
        self.assertIsNotNone(thread)
        self.assertEqual(thread.subject, 'hello there')
        self.assertEqual(thread.status, 'ai_handling')
        self.assertEqual(thread.kind, 'general')

        roles = list(thread.messages.values_list('role', flat=True))
        self.assertEqual(roles, ['user', 'ai'])
        ai_reply = thread.messages.get(role='ai')
        self.assertIn('Greetings, Novarian', ai_reply.body)
        self.assertIsNone(ai_reply.author)

    def test_issue_signal_gets_tracking_and_flag(self):
        _, thread = self._start('The market page is broken for me')
        thread.refresh_from_db()
        self.assertEqual(thread.kind, 'issue')
        self.assertEqual(thread.status, 'ai_handling')
        ai_reply = thread.messages.get(role='ai')
        self.assertIn('TN-0001', ai_reply.body)

    def test_escalate_via_message_moves_to_agents(self):
        _, thread = self._start('hello')
        self.client.post(
            reverse('terra:chat_send', args=[thread.id]),
            {'body': 'I want to speak to a human'},
        )
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'escalated')
        self.assertTrue(
            thread.messages.filter(
                role='system',
                body__contains='Novarian agent network',
            ).exists(),
        )
        self.assertTrue(
            thread.messages.filter(role='ai', body__contains='agent').exists(),
        )

    def test_resolve_action_and_reopen_on_reply(self):
        _, thread = self._start('hello')
        self.client.post(
            reverse('terra:chat_action', args=[thread.id]),
            {'action': 'resolve'},
        )
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'resolved')
        self.assertTrue(
            thread.messages.filter(
                role='system', body__contains='marked resolved',
            ).exists(),
        )

        self.client.post(
            reverse('terra:chat_send', args=[thread.id]),
            {'body': 'actually thanks, one more thing'},
        )
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'ai_handling')
        self.assertTrue(
            thread.messages.filter(
                role='system', body__contains='reopened',
            ).exists(),
        )

    def test_confirm_resolved_by_message(self):
        _, thread = self._start('the market page has a bug')
        thread.refresh_from_db()
        self.assertEqual(thread.kind, 'issue')
        self.client.post(
            reverse('terra:chat_send', args=[thread.id]),
            {'body': 'this is solved, thank you'},
        )
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'resolved')

    # ---- Novarian agents ----

    def test_agent_reads_replies_and_claims_thread(self):
        _, thread = self._start('I need to signal an issue. It is broken.')
        agent = self._user('helper', agent=True)

        self.client.force_login(agent)
        response = self.client.get(reverse('terra:chat_thread', args=[thread.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'I need to signal an issue')

        self.client.post(
            reverse('terra:chat_send', args=[thread.id]),
            {'body': 'Novarian agent here — checking your signal now.'},
        )
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'escalated')
        self.assertEqual(thread.assigned_agent, agent)
        agent_msg = thread.messages.filter(role='agent').first()
        self.assertIn('checking your signal', agent_msg.body)
        self.assertEqual(agent_msg.author, agent)
        self.assertTrue(
            thread.messages.filter(
                role='system', body__contains='joined the thread',
            ).exists(),
        )

        # the owner still sees AI replies after the hand-off
        self.client.force_login(thread.user)
        self.client.post(
            reverse('terra:chat_send', args=[thread.id]),
            {'body': 'what does the market page show?'},
        )
        self.assertTrue(thread.messages.filter(role='ai').count() >= 2)

    def test_thread_hidden_from_other_novarians(self):
        _, thread = self._start('hello')
        stranger = self._user('stranger')
        self.client.force_login(stranger)
        response = self.client.get(
            reverse('terra:chat_thread', args=[thread.id]),
        )
        self.assertEqual(response.status_code, 404)

    def test_agent_desk_queue(self):
        _, thread = self._start('signal me please, something is wrong')
        thread.refresh_from_db()
        self.assertEqual(thread.status, 'ai_handling')

        # plain Novarian is refused
        stranger = self._user('nosy')
        self.client.force_login(stranger)
        response = self.client.get(reverse('terra:chat_agent'))
        self.assertEqual(response.status_code, 403)

        # an escalated signal shows up for the agent
        thread.status = 'escalated'
        thread.save()
        agent = self._user('helper', agent=True)
        self.client.force_login(agent)
        response = self.client.get(reverse('terra:chat_agent'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agent desk')
        self.assertContains(response, thread.subject)
        self.assertContains(response, 'signal me please')

    # ---- polling + engine ----

    def test_poll_endpoint_returns_new_messages_only(self):
        _, thread = self._start('hello there')
        url = reverse('terra:chat_messages', args=[thread.id])

        response = self.client.get(url, {'after': 0})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'ai_handling')
        self.assertEqual(len(data['messages']), 2)
        self.assertEqual(data['messages'][0]['name'], 'novarian')
        self.assertEqual(data['messages'][1]['name'], 'Terra AI')
        last_id = data['messages'][-1]['id']

        response = self.client.get(url, {'after': last_id})
        self.assertEqual(response.json()['messages'], [])

        stranger = self._user('eavesdropper')
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(url, {'after': 0}).status_code, 404)

    def test_ai_engine_classifies_and_answers(self):
        from terra.chat_ai import classify, respond

        self.assertEqual(classify('hello'), 'greeting')
        self.assertEqual(classify('the checkout is broken'), 'issue')
        self.assertEqual(classify('what is the terrax price'), 'market')
        self.assertEqual(classify('escalate please'), 'escalate')
        self.assertEqual(classify('it is solved now'), 'confirm_resolved')
        self.assertEqual(classify('how much does priority cost'), 'services')
        self.assertEqual(classify('asdlfkj qwerty'), 'fallback')

        thread = ChatThread(id=99, subject='probe')
        intent, reply = respond('what is the terrax price', thread)
        self.assertEqual(intent, 'market')
        self.assertIn('1.25', reply)

        _, issue_reply = respond('it is broken', thread)
        self.assertIn('TN-0099', issue_reply)

        _, fallback = respond('zzzz', thread)
        self.assertIn('I can help with', fallback)


class WeatherTests(TestCase):
    """Weather page, the week-long heat simulation and push plumbing."""

    def test_weather_page_renders_conditions_and_controls(self):
        response = self.client.get(reverse('terra:weather'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'wx-now__temp')
        self.assertContains(response, 'wx-banner')          # today's heat alert
        self.assertContains(response, 'Heat simulation')
        self.assertContains(response, 'Enable push alerts')
        self.assertContains(response, 'Trigger heat alert now')
        self.assertContains(response, 'csrfmiddlewaretoken')  # fetch needs it
        for name in ['Aurelia Basin', 'Vermilion Steps',
                     'The Glass Tundra', 'Pelagos Deep']:
            self.assertContains(response, name)
        # the simulation strip shows all eight days
        self.assertEqual(response.content.decode().count('wx-day '), 8)

    def test_simulation_creates_at_least_a_week_of_alerts(self):
        from terra.weather import ensure_alerts

        created = ensure_alerts()
        self.assertEqual(len(created), 8)
        self.assertEqual(ensure_alerts(), [])  # idempotent

        alerts = list(WeatherAlert.objects.order_by('day'))
        self.assertEqual(len(alerts), 8)
        today = timezone.localdate()
        days = [a.day for a in alerts]
        self.assertEqual(min(days), today)
        self.assertEqual((max(days) - min(days)).days, 7)

        # every single day crosses the threshold → one trigger per day
        for alert in alerts:
            self.assertGreaterEqual(alert.anomaly, Decimal('7'))
            self.assertIn(alert.severity, ('elevated', 'high', 'extreme'))
            self.assertTrue(alert.message)
        self.assertIn('extreme', {a.severity for a in alerts})

    def test_status_endpoint_serves_alerts(self):
        response = self.client.get(reverse('terra:weather_status'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('temp', data['now'])
        self.assertEqual(len(data['sectors']), 4)
        self.assertGreaterEqual(len(data['alerts']), 8)
        self.assertGreaterEqual(data['alert_total'], 8)
        first = data['alerts'][0]
        for key in ('id', 'day', 'severity', 'temp', 'headline', 'message'):
            self.assertIn(key, first)

        last_id = data['alerts'][-1]['id']
        response = self.client.get(
            reverse('terra:weather_status'), {'after': last_id},
        )
        self.assertEqual(response.json()['alerts'], [])

    def test_trigger_endpoint_is_post_only(self):
        response = self.client.get(reverse('terra:weather_trigger'))
        self.assertEqual(response.status_code, 405)

        response = self.client.post(reverse('terra:weather_trigger'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_simulation'])
        self.assertIn(data['severity'], ('elevated', 'high', 'extreme'))
        for key in ('id', 'headline', 'message', 'temp', 'day'):
            self.assertIn(key, data)
        self.assertIn('°C', data['message'])

    def test_map_page_renders_3d_terrain(self):
        response = self.client.get(reverse('terra:map'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # scene chrome: canvas renderer, HUD, toolbar, compass, JSON payload
        for marker in (
            'map-scene', 'data-map-canvas', 'map-hud', 'map-toolbar',
            'map-compass', 'map-readout', 'data-layer="relief"',
            'data-layer="routes"', 'data-layer="heat"', 'tn-map-data',
            'js/map.js', 'css/map.css', 'mappage__credits',
        ):
            self.assertIn(marker, html)
        # four beacons carry their world anchors + live conditions
        for key in ['aurelia', 'vermilion', 'glasslands', 'pelagos']:
            self.assertIn(f'pin--{key}', html)
            self.assertIn(f'data-sector="{key}"', html)
        self.assertIn('data-wx=', html)
        self.assertIn('data-wy=', html)
        # the old static extrusion is gone
        self.assertNotIn('tn-layer', html)
        self.assertNotIn('globe3d__plane', html)
        # sector payload is valid JSON with coordinates + live temps
        payload = json.loads(
            html.split('id="tn-map-data">')[1].split('</script>')[0],
        )
        self.assertEqual(len(payload), 4)
        for entry in payload:
            for field in ('key', 'name', 'temp', 'humidity', 'wind',
                          'condition', 'icon', 'wx', 'wy', 'mine'):
                self.assertIn(field, entry)

    def test_map_renderer_module_is_valid_js(self):
        js = Path(settings.BASE_DIR, 'static', 'js', 'map.js').read_text()
        # pure math module exports for headless testing
        self.assertIn('var TNMap', js)
        self.assertIn('buildTerrain', js)
        self.assertIn('makeCamera', js)
        self.assertIn('module.exports = TNMap', js)
        # runtime pieces
        for marker in (
            'data-map-canvas', 'prefers-reduced-motion', 'pointerdown',
            'wheel', 'IntersectionObserver', 'data-layer', 'data-hud-temp',
        ):
            self.assertIn(marker, js)

    def test_notification_plumbing_exists(self):
        weather_js = Path(settings.BASE_DIR, 'static', 'js', 'weather.js').read_text()
        self.assertIn('Notification.requestPermission', weather_js)
        self.assertIn('showNotification', weather_js)
        self.assertIn('terra-notified-days', weather_js)   # once-per-day guard
        self.assertIn('X-CSRFToken', weather_js)

        sw = Path(settings.BASE_DIR, 'serviceworker.js').read_text()
        self.assertIn('notificationclick', sw)
        self.assertIn("'push'", sw)
        self.assertIn('showNotification', sw)
        self.assertIn('/weather/', sw)
        self.assertIn("VERSION = 'v3'", sw)

    def test_nav_and_footer_link_weather_and_map(self):
        home = self.client.get(reverse('terra:home'))
        self.assertContains(home, reverse('terra:weather'))
        self.assertContains(home, reverse('terra:map'))

    # ---- web push (django-pwa-webpush) ----

    def _push_payload(self, endpoint='https://push.example/sub-1'):
        return {
            'status_type': 'subscribe',
            'browser': 'Chrome',
            'subscription': {
                'endpoint': endpoint,
                'keys': {'auth': 'a' * 27, 'p256dh': 'p' * 27},
            },
        }

    def _post_subscription(self, payload):
        return self.client.post(
            reverse('save_webpush_info'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def _seed_subscription(self, endpoint='https://push.example/seed'):
        from pwa_webpush.models import PushInformation, SubscriptionInfo

        user = User.objects.create_user(
            'pushfan', 'pushfan@example.com', 'push-pass-99x',
        )
        sub = SubscriptionInfo.objects.create(
            browser='Chrome',
            endpoint=endpoint,
            auth='auth-token-0000000000000000',
            p256dh='p256-key-0000000000000000',
        )
        PushInformation.objects.create(user=user, subscription=sub)
        return user, sub

    def test_push_endpoint_saves_subscription_for_reader(self):
        from pwa_webpush.models import PushInformation, SubscriptionInfo

        user = User.objects.create_user(
            'pusher', 'pusher@example.com', 'push-pass-99x',
        )
        self.client.force_login(user)
        response = self._post_subscription(self._push_payload())
        self.assertEqual(response.status_code, 201)
        self.assertEqual(SubscriptionInfo.objects.count(), 1)
        info = PushInformation.objects.get()
        self.assertEqual(info.user, user)
        self.assertEqual(
            info.subscription.endpoint,
            'https://push.example/sub-1',
        )
        # repeating the same subscription stays idempotent
        again = self._post_subscription(self._push_payload())
        self.assertEqual(again.status_code, 201)
        self.assertEqual(PushInformation.objects.count(), 1)

    def test_push_endpoint_rejects_anonymous_readers(self):
        from pwa_webpush.models import PushInformation

        response = self._post_subscription(self._push_payload())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PushInformation.objects.count(), 0)

    def test_weather_trigger_broadcasts_to_subscribers(self):
        from pwa_webpush.models import PushInformation

        self._seed_subscription()
        with patch('terra.push.send_to_subscription') as send:
            response = self.client.post(reverse('terra:weather_trigger'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['is_simulation'])
        # a fresh database seeds the 8-day window first (one broadcast),
        # then the demo fires its own push.
        self.assertGreaterEqual(data['push_sent'], 1)
        self.assertTrue(send.called)
        sim_calls = [
            str(call.args[1])
            for call in send.call_args_list
            if 'terra-sim-' in str(call.args[1])
        ]
        self.assertTrue(sim_calls, 'the demo push must carry its tag')
        payload = sim_calls[0]
        self.assertIn('"headline"', payload)
        self.assertIn('"message"', payload)
        self.assertEqual(PushInformation.objects.count(), 1)

    def test_broadcast_prunes_subscriptions_revoked_by_the_browser(self):
        from pywebpush import WebPushException

        from terra.push import broadcast_push

        self._seed_subscription(endpoint='https://push.example/dead')

        def revoke(*args, **kwargs):
            raise WebPushException('Gone', response=Mock(status_code=410))

        with patch('terra.push.send_to_subscription', side_effect=revoke):
            sent = broadcast_push('Title', 'Body')
        self.assertEqual(sent, 0)
        # 410 → the dead subscription rows are removed (cascade)
        from pwa_webpush.models import PushInformation, SubscriptionInfo

        self.assertEqual(SubscriptionInfo.objects.count(), 0)
        self.assertEqual(PushInformation.objects.count(), 0)

    def test_broadcast_is_a_noop_without_subscribers(self):
        from terra.push import broadcast_push

        with patch('terra.push.send_to_subscription') as send:
            sent = broadcast_push('Title', 'Body')
        self.assertEqual(sent, 0)
        send.assert_not_called()


class NewsTests(TestCase):
    """News section: seeded newsroom, filters, article pages, nav links."""

    def test_news_page_renders_lead_story_and_stream(self):
        response = self.client.get(reverse('terra:news'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in ('nws-lead', 'nws-grid', 'nws-chip', 'nws-filters',
                       'css/news.css', 'Newsroom'):
            self.assertIn(marker, html)
        # the featured dispatch leads the page
        self.assertContains(
            response, 'Expedition 01 boarding window opens',
        )
        # every other dispatch is listed in the archive
        self.assertContains(response, 'Heat wave holds')
        self.assertContains(response, 'TerraX steadies')

    def test_exactly_twenty_dispatches_are_seeded(self):
        from terra.news import NEWS_ITEMS, ensure_news

        created = ensure_news()
        self.assertEqual(created, [])          # migration already seeded them
        self.assertEqual(NewsItem.objects.count(), 20)
        self.assertEqual(len(NEWS_ITEMS), 20)
        # second run is idempotent — no duplicates
        self.assertEqual(ensure_news(), [])
        self.assertEqual(NewsItem.objects.count(), 20)

    def test_seeder_creates_missing_dispatches_only(self):
        from terra.news import ensure_news

        NewsItem.objects.all().delete()
        created = ensure_news()
        self.assertEqual(len(created), 20)
        self.assertEqual(NewsItem.objects.count(), 20)
        self.assertEqual(
            len({n.slug for n in NewsItem.objects.all()}), 20,
        )                                     # slugs are unique

    def test_dispatches_cover_the_colony_desks(self):
        categories = set(
            NewsItem.objects.values_list('category', flat=True),
        )
        # all seven desks represented
        self.assertEqual(
            categories,
            {'expedition', 'weather', 'market', 'transport',
             'civic', 'health', 'science'},
        )
        # exactly one lead story, and it is published most recently first
        self.assertEqual(
            NewsItem.objects.filter(is_featured=True).count(), 1,
        )
        for item in NewsItem.objects.all():
            self.assertTrue(item.title)
            self.assertTrue(item.summary)
            self.assertGreaterEqual(len(item.body.split('\n\n')), 3)
            self.assertGreaterEqual(item.reading_minutes, 1)

    def test_category_filter_narrows_the_stream(self):
        response = self.client.get(reverse('terra:news'), {'category': 'transport'})
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, 'Night rails return')
        self.assertContains(response, 'Second bus line')
        self.assertNotIn('Heat wave holds', html)

    def test_unknown_category_falls_back_to_the_full_wire(self):
        response = self.client.get(
            reverse('terra:news'), {'category': 'nonsense'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Heat wave holds')

    def test_article_page_renders_paragraphs_and_related(self):
        item = NewsItem.objects.get(slug='heat-wave-eight-day-anomaly-forecast')
        response = self.client.get(
            reverse('terra:news_detail', args=[item.slug]),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, item.title)
        self.assertContains(response, 'nws-article__body')
        # body splits into distinct paragraphs
        self.assertEqual(response.context['paragraphs'][0][:30],
                         item.body.split('\n\n')[0][:30])
        self.assertGreaterEqual(len(response.context['paragraphs']), 3)
        # a weather sibling is offered beneath the article
        self.assertIn('related', response.context)
        self.assertNotIn(item, response.context['related'])
        self.assertIn('css/news.css', html)

    def test_unknown_slug_404s(self):
        response = self.client.get(
            reverse('terra:news_detail', args=['no-such-dispatch']),
        )
        self.assertEqual(response.status_code, 404)

    def test_nav_and_footer_link_to_news(self):
        home = self.client.get(reverse('terra:news'))
        self.assertContains(home, reverse('terra:news'))
        landing = self.client.get(reverse('terra:home'))
        self.assertContains(landing, reverse('terra:news'))

    # ---- reader comments ----

    SLUG = 'heat-wave-eight-day-anomaly-forecast'

    def _login(self, username='reader'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'news-pass-77x',
        )
        self.client.force_login(user)
        return user

    def test_comment_section_renders_on_the_article(self):
        response = self.client.get(
            reverse('terra:news_detail', args=[self.SLUG]),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('nws-comments', html)
        self.assertIn('nws-comments__empty', html)      # empty state
        # anonymous readers get a sign-in prompt, not the form
        self.assertIn(reverse('terra:login'), html)
        self.assertNotIn('id-news-comment', html)

    def test_signed_in_reader_gets_the_comment_form(self):
        self._login()
        page = self.client.get(
            reverse('terra:news_detail', args=[self.SLUG]),
        )
        self.assertContains(page, 'id-news-comment')
        self.assertContains(page, 'Post comment')
        self.assertContains(
            page, reverse('terra:news_comment', args=[self.SLUG]),
        )

    def test_anonymous_comment_redirects_to_login(self):
        response = self.client.post(
            reverse('terra:news_comment', args=[self.SLUG]),
            {'body': 'hello from orbit'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])
        self.assertEqual(NewsComment.objects.count(), 0)

    def test_comment_posts_displays_and_counts(self):
        self._login()
        body = 'Eight days of anomalies — hydrate, Novarians.'
        response = self.client.post(
            reverse('terra:news_comment', args=[self.SLUG]),
            {'body': body},
        )
        self.assertRedirects(
            response, reverse('terra:news_detail', args=[self.SLUG]),
        )
        comment = NewsComment.objects.get()
        self.assertEqual(comment.body, body)
        self.assertEqual(comment.user.username, 'reader')

        page = self.client.get(
            reverse('terra:news_detail', args=[self.SLUG]),
        )
        self.assertContains(page, body)                  # the comment itself
        self.assertContains(page, 'reader')              # the author
        self.assertContains(page, '1 comment')           # plural heading (en)
        self.assertNotIn('nws-comments__empty', page.content.decode())

    def test_blank_comment_is_rejected(self):
        self._login()
        self.client.post(
            reverse('terra:news_comment', args=[self.SLUG]),
            {'body': '    '},
        )
        self.assertEqual(NewsComment.objects.count(), 0)

    def test_long_comments_are_capped_at_1000_characters(self):
        self._login()
        self.client.post(
            reverse('terra:news_comment', args=[self.SLUG]),
            {'body': 'x' * 1500},
        )
        self.assertEqual(len(NewsComment.objects.get().body), 1000)

    # ---- the week-long archive + translated content ----

    NEW_WEEK_SLUGS = (
        'lagoon-array-completes-southern-sweep',
        'welcome-bonus-wallets-pass-ten-thousand',
        'council-publishes-second-season-levies',
        'night-rails-ten-thousand-riders',
        'warm-spell-to-ease-as-window-closes',
        'heat-strain-drills-run-in-every-village',
        'manifest-passes-the-halfway-mark',
        'glass-tundra-ice-core-dated',
        'first-month-of-pensions-settles-clean',
        'terra-watch-beacon-links-to-terra-chat',
    )

    def test_the_archive_spans_a_full_week(self):
        now = timezone.localtime()
        fresh = NewsItem.objects.filter(slug__in=self.NEW_WEEK_SLUGS)
        self.assertEqual(fresh.count(), 10)
        for item in fresh:
            age = now - item.published_at
            self.assertGreaterEqual(age, timedelta(hours=107))
            self.assertLessEqual(age, timedelta(hours=168, minutes=5))
        oldest = NewsItem.objects.order_by('published_at').first()
        self.assertGreaterEqual(
            now - oldest.published_at, timedelta(days=6, hours=22),
        )
        # strictly newest-first ordering across the whole wire
        published = list(
            NewsItem.objects.values_list('published_at', flat=True),
        )
        self.assertEqual(published, sorted(published, reverse=True))

    def test_news_page_content_translates_to_french(self):
        self.client.cookies['django_language'] = 'fr'
        response = self.client.get(reverse('terra:news'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # the lead headline resolves through the newsroom filter …
        # (apostrophes are HTML-escaped, so probe without them)
        self.assertIn('Expédition 01 ouvre sa fenêtre', html)
        # … and the English msgid no longer leaks into the page
        self.assertNotIn(
            'Expedition 01 boarding window opens for the first', html,
        )


class FeedbackTests(TestCase):
    """The Feedback page: file an insight, read the crew's wall."""

    def _login(self, username='novarian'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'signal-pass-31x',
        )
        self.client.force_login(user)
        return user

    def test_feedback_page_renders_with_empty_state(self):
        response = self.client.get(reverse('terra:feedback'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No insights on the wall yet')
        self.assertContains(response, 'Council inbox')
        self.assertContains(response, 'to file an insight')

    def test_anonymous_post_redirects_to_login(self):
        response = self.client.post(
            reverse('terra:feedback_post'),
            {'topic': 'idea', 'body': 'Night buses should run later.'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])
        self.assertEqual(Feedback.objects.count(), 0)

    def test_signed_in_novarian_files_an_insight(self):
        user = self._login()
        response = self.client.post(
            reverse('terra:feedback_post'),
            {'topic': 'balance',
             'body': 'The 0.5% exchange fee feels fair — keep it.'},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        entry = Feedback.objects.get()
        self.assertEqual(entry.user, user)
        self.assertEqual(entry.topic, 'balance')
        # back on the wall, marked as yours
        self.assertContains(response, 'The 0.5% exchange fee feels fair')
        self.assertContains(response, 'Yours')

    def test_empty_insight_is_rejected(self):
        self._login()
        self.client.post(
            reverse('terra:feedback_post'),
            {'topic': 'idea', 'body': '   '},
        )
        self.assertEqual(Feedback.objects.count(), 0)

    def test_unknown_topic_falls_back_to_idea(self):
        self._login()
        self.client.post(
            reverse('terra:feedback_post'),
            {'topic': 'nonsense', 'body': 'Add a canteen to the night train.'},
        )
        self.assertEqual(Feedback.objects.get().topic, 'idea')

    def test_novarians_see_each_others_insights(self):
        ada = User.objects.create_user(
            'ada', 'ada@example.com', 'pw-ada-99x', first_name='Ada',
        )
        Feedback.objects.create(
            user=ada, topic='fault',
            body='The market filter resets after every trade.',
        )
        self._login()
        response = self.client.get(reverse('terra:feedback'))
        self.assertContains(response, 'The market filter resets after every trade.')
        self.assertContains(response, 'Ada')          # author from another novarian
        self.assertContains(response, '1 insight')    # pluralised heading

    def test_feedback_link_sits_in_the_navigation(self):
        response = self.client.get(reverse('terra:home'))
        self.assertContains(response, reverse('terra:feedback'))


class CivicTests(TestCase):
    """Government portal: taxation, requests, records, pension, waste."""

    def _user(self, username='citizen', trx='5.000000', sector='aurelia'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'civic-pass-88x',
        )
        Profile.objects.create(
            user=user, sector=sector, trx_balance=Decimal(trx),
        )
        self.client.force_login(user)
        return user

    # ---- access & rendering ----

    def test_portal_requires_login(self):
        response = self.client.get(reverse('terra:government'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_portal_renders_all_five_services(self):
        self._user()
        response = self.client.get(reverse('terra:government'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertContains(response, 'civic.css')
        self.assertContains(response, 'The <em>fiscal levy.</em>')
        self.assertContains(response, 'Request road upgrade')
        self.assertContains(response, 'Waste management')
        self.assertContains(response, 'Social security')
        self.assertContains(response, 'Pension desk')
        self.assertContains(response, 'SSN-TN-')
        self.assertContains(response, 'Payment history')
        # a bill for the current fiscal period exists and is unpaid
        bill = TaxBill.objects.get(user__username='citizen')
        self.assertEqual(bill.status, 'unpaid')
        self.assertIn(f'FY{timezone.localdate().year}', bill.code)

    def test_tax_schedule_matches_engine(self):
        from terra.civic import TAX_SCHEDULE, tax_amount

        user = self._user(trx='9.000000')
        profile = Profile.objects.get(user=user)
        self.assertEqual(tax_amount(profile), TAX_SCHEDULE['aurelia'])
        profile.priority = True
        profile.save()
        profile.refresh_from_db()
        self.assertEqual(
            tax_amount(profile),
            TAX_SCHEDULE['aurelia'] + Decimal('0.150000'),
        )

    # ---- taxation ----

    def test_pay_tax_settles_bill_and_writes_ledger(self):
        user = self._user(trx='10.000000')
        response = self.client.post(reverse('terra:tax_pay'), follow=True)
        self.assertRedirects(response, reverse('terra:government'))

        profile = Profile.objects.get(user=user)
        bill = TaxBill.objects.get(user=user)
        self.assertEqual(bill.status, 'paid')
        self.assertIsNotNone(bill.paid_at)
        self.assertEqual(profile.trx_balance, Decimal('10.000000') - bill.amount_trx)

        tx = Transaction.objects.get(user=user)
        self.assertEqual(tx.kind, 'tax')
        self.assertLess(tx.trx, 0)
        self.assertIn(bill.code, tx.note)
        self.assertContains(response, 'SETTLED')

        # paying again must not double charge
        self.client.post(reverse('terra:tax_pay'), follow=True)
        self.assertEqual(Transaction.objects.filter(user=user).count(), 1)

    def test_pay_tax_requires_funds(self):
        user = self._user(trx='0.000001')
        self.client.post(reverse('terra:tax_pay'), follow=True)

        profile = Profile.objects.get(user=user)
        bill = TaxBill.objects.get(user=user)
        self.assertEqual(bill.status, 'unpaid')
        self.assertEqual(profile.trx_balance, Decimal('0.000001'))
        self.assertEqual(Transaction.objects.filter(user=user).count(), 0)

    # ---- road & waste requests ----

    def test_road_request_gets_tracking_and_evolving_status(self):
        self._user()
        self.client.post(reverse('terra:civic_request'), {
            'category': 'road', 'sector': 'aurelia',
            'location': 'Basin Ring Road, km 4',
            'detail': 'Crater-sized pothole after the dust storm.',
            'next': 'government',
        }, follow=True)

        request_obj = CivicRequest.objects.get(user__username='citizen')
        self.assertEqual(request_obj.category, 'road')
        self.assertTrue(request_obj.tracking.startswith('GR-'))
        self.assertEqual(request_obj.status_label, 'Received')

        response = self.client.get(reverse('terra:government'))
        self.assertContains(response, request_obj.tracking)
        self.assertContains(response, 'Basin Ring Road')

        # status advances with age — no cron required
        CivicRequest.objects.filter(pk=request_obj.pk).update(
            created_at=timezone.now() - timedelta(hours=48),
        )
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status_label, 'Scheduled')
        self.assertEqual(request_obj.status_slug, 'scheduled')

    def test_request_validation(self):
        self._user()
        for payload in (
            {'category': 'nope', 'sector': 'aurelia', 'location': 'Somewhere'},
            {'category': 'road', 'sector': 'atlantis', 'location': 'Somewhere'},
            {'category': 'road', 'sector': 'aurelia', 'location': 'x'},
        ):
            self.client.post(reverse('terra:civic_request'), payload, follow=True)
        self.assertEqual(CivicRequest.objects.count(), 0)

    def test_waste_request_and_sector_schedule(self):
        from terra.civic import waste_schedule

        self._user(sector='vermilion')
        schedule = waste_schedule('vermilion')
        self.assertIn('Wed', schedule['days'])
        self.assertIn(schedule['next'].weekday(), (2, 5))
        self.assertLessEqual(schedule['in_days'], 6)

        self.client.post(reverse('terra:civic_request'), {
            'category': 'waste', 'sector': 'vermilion',
            'location': 'Habitat 12, east platform',
            'detail': 'Bulk metal scrap.',
            'next': 'government',
        }, follow=True)

        obj = CivicRequest.objects.get(user__username='citizen')
        self.assertTrue(obj.tracking.startswith('WM-'))
        response = self.client.get(reverse('terra:government'))
        self.assertContains(response, 'Waste management')
        self.assertContains(response, obj.tracking)

    # ---- social security + pension ----

    def test_dob_filing_and_pension_claim(self):
        user = self._user()
        response = self.client.get(reverse('terra:government'))
        self.assertContains(response, 'No date of birth on file')

        self.client.post(reverse('terra:civic_profile'), {
            'date_of_birth': '1955-04-09',
        }, follow=True)
        profile = Profile.objects.get(user=user)
        self.assertIsNotNone(profile.date_of_birth)

        response = self.client.get(reverse('terra:government'))
        self.assertContains(response, 'Eligible · age')
        self.assertContains(response, 'Claim 0.600000 TRX pension')

        self.client.post(reverse('terra:pension_claim'), follow=True)
        profile.refresh_from_db()
        self.assertEqual(profile.trx_balance, Decimal('5.600000'))
        pension_tx = Transaction.objects.get(user=user, kind='pension')
        self.assertGreater(pension_tx.trx, 0)

        # once per calendar month
        self.client.post(reverse('terra:pension_claim'), follow=True)
        self.assertEqual(
            Transaction.objects.filter(user=user, kind='pension').count(), 1,
        )

    def test_pension_blocked_for_underage_and_bad_dates(self):
        user = self._user(username='youngling')
        self.client.post(reverse('terra:civic_profile'), {
            'date_of_birth': '2010-06-01',
        }, follow=True)

        response = self.client.get(reverse('terra:government'))
        self.assertContains(response, 'months to eligibility')

        self.client.post(reverse('terra:pension_claim'), follow=True)
        self.assertEqual(Transaction.objects.filter(user=user).count(), 0)

        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.client.post(reverse('terra:civic_profile'), {
            'date_of_birth': tomorrow,
        }, follow=True)
        profile = Profile.objects.get(user=user)
        self.assertEqual(
            profile.date_of_birth.isoformat(), '2010-06-01',
        )


class HealthTests(TestCase):
    """Health portal: Terra Watch, medical requests, nearest facilities."""

    def _user(self, username='patient', trx='60.000000', sector='aurelia'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'health-pass-91x',
        )
        Profile.objects.create(
            user=user, sector=sector, trx_balance=Decimal(trx),
        )
        self.client.force_login(user)
        return user

    def test_health_requires_login(self):
        response = self.client.get(reverse('terra:health'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_health_page_offers_watch_and_facilities(self):
        self._user()
        response = self.client.get(reverse('terra:health'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'civic.css')
        self.assertContains(response, 'Terra Watch')
        self.assertContains(response, '50.000000 TRX')
        self.assertContains(response, 'Buy Terra Watch')
        self.assertContains(response, 'Nearby care')
        self.assertContains(response, 'Nova Central Hospital')
        self.assertContains(response, 'hlt-facilities')
        self.assertNotContains(response, 'Today’s reading')  # not owned yet

    def test_buy_terra_watch_pairs_and_tracks(self):
        user = self._user(trx='60.000000')
        response = self.client.post(reverse('terra:terra_watch'), follow=True)
        self.assertRedirects(response, reverse('terra:health'))

        profile = Profile.objects.get(user=user)
        self.assertTrue(profile.terra_watch)
        self.assertEqual(profile.trx_balance, Decimal('10.000000'))

        tx = Transaction.objects.get(user=user)
        self.assertEqual(tx.kind, 'service')
        self.assertEqual(tx.trx, Decimal('-50.000000'))
        self.assertIn('Terra Watch', tx.note)

        response = self.client.get(reverse('terra:health'))
        self.assertContains(response, 'Paired · streaming')
        self.assertContains(response, 'Today’s reading')
        self.assertContains(response, 'TW-')          # device id
        self.assertContains(response, 'Heart rate')

        # idempotent — no double purchase
        self.client.post(reverse('terra:terra_watch'), follow=True)
        profile.refresh_from_db()
        self.assertEqual(profile.trx_balance, Decimal('10.000000'))
        self.assertEqual(Transaction.objects.filter(user=user).count(), 1)

    def test_buy_terra_watch_requires_funds(self):
        user = self._user(trx='20.000000')
        self.client.post(reverse('terra:terra_watch'), follow=True)

        profile = Profile.objects.get(user=user)
        self.assertFalse(profile.terra_watch)
        self.assertEqual(profile.trx_balance, Decimal('20.000000'))
        self.assertEqual(Transaction.objects.filter(user=user).count(), 0)

    def test_medical_request_tracked_on_health_page(self):
        self._user(sector='pelagos')
        self.client.post(reverse('terra:civic_request'), {
            'category': 'medical', 'sector': 'pelagos',
            'location': 'Home visit',
            'detail': 'Persistent headache since the heat spike.',
            'next': 'health',
        }, follow=True)

        obj = CivicRequest.objects.get(user__username='patient')
        self.assertTrue(obj.tracking.startswith('MD-'))
        self.assertEqual(obj.status_label, 'Received')

        response = self.client.get(reverse('terra:health'))
        self.assertContains(response, obj.tracking)
        self.assertContains(response, 'Home visit')

    def test_nearest_facility_is_in_home_sector(self):
        from terra.civic import facilities_for

        user = self._user(sector='pelagos')
        rows = facilities_for(user)
        distances = [row['distance'] for row in rows]
        self.assertEqual(distances, sorted(distances))
        self.assertTrue(rows[0]['is_home'])
        self.assertLessEqual(rows[0]['distance'], 4.5)
        self.assertGreaterEqual(rows[1]['distance'], 6.0)
        self.assertEqual(len(rows), 5)

    def test_vitals_are_daily_and_deterministic(self):
        from terra.civic import vitals

        user = self._user()
        first = vitals(user)
        second = vitals(user)
        self.assertEqual(first, second)
        for key in ('heart_rate', 'spo2', 'sleep', 'steps',
                    'stress', 'readiness', 'device', 'bars'):
            self.assertIn(key, first)
        self.assertEqual(len(first['bars']), 7)
        self.assertTrue(first['device'].startswith('TW-'))


class TransportTests(TestCase):
    """Transport: welcome bonus, live timetable, fares and QR tickets."""

    def _user(self, username='rider', trx='100.000000', sector='aurelia'):
        user = User.objects.create_user(
            username, f'{username}@example.com', 'transit-pass-44x',
        )
        Profile.objects.create(
            user=user, sector=sector, trx_balance=Decimal(trx),
        )
        Traveler.objects.create(
            user=user, name=username.capitalize(), relation='self',
        )
        self.client.force_login(user)
        return user

    # ---- welcome bonus ----

    def test_signup_grants_10k_welcome_bonus(self):
        response = self.client.post(reverse('terra:signup'), {
            'username': 'freshrider', 'email': 'fresh@example.com',
            'first_name': 'Nova Rider',
            'password1': 'lunar-tide-42x', 'password2': 'lunar-tide-42x',
        }, follow=True)

        profile = Profile.objects.get(user__username='freshrider')
        self.assertEqual(profile.trx_balance, Decimal('10000.000000'))
        bonus = Transaction.objects.get(user=profile.user, kind='bonus')
        self.assertEqual(bonus.trx, Decimal('10000.000000'))
        self.assertIn('Welcome bonus', bonus.note)

        messages_list = [str(m) for m in response.context['messages']]
        self.assertTrue(
            any('Welcome bonus' in m for m in messages_list), messages_list,
        )
        # and it is visible on the ledger at the market page
        market = self.client.get(reverse('terra:market'))
        self.assertContains(market, 'Welcome bonus')

    # ---- access & board ----

    def test_transport_requires_login(self):
        response = self.client.get(reverse('terra:transport'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('terra:login'), response['Location'])

    def test_board_shows_balance_village_and_departures(self):
        self._user(trx='100.000000', sector='aurelia')
        response = self.client.get(reverse('terra:transport'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertContains(response, 'transport.css')
        self.assertContains(response, '100.000000')          # balance at top
        self.assertContains(response, 'Wallet · TerraX')
        self.assertContains(response, 'Habitat 12')           # the village
        self.assertContains(response, 'Departs in')
        self.assertContains(response, 'Buy a fare')
        self.assertContains(response, 'Family travellers')
        self.assertContains(response, 'Continental Express')  # trains stop here
        self.assertContains(response, 'Basin Loop Bus')       # village bus
        self.assertGreaterEqual(html.count('data-countdown='), 6)
        self.assertContains(response, 'transport.js')

        # a Self traveller exists automatically
        traveler = Traveler.objects.get(user__username='rider')
        self.assertEqual(traveler.relation, 'self')

    def test_timetable_is_future_sorted_and_mixed(self):
        from terra.transit import timetable

        board = timetable('vermilion')
        epochs = [row['epoch'] for row in board]
        self.assertEqual(epochs, sorted(epochs))
        now = timezone.localtime().timestamp()
        self.assertTrue(all(epoch > now for epoch in epochs))
        kinds = {row['kind'] for row in board}
        self.assertEqual(kinds, {'bus', 'train'})
        self.assertTrue(all('|' in row['value'] for row in board))
        self.assertLessEqual(len(board), 10)

    def test_timetable_tomorrow_block_tolerates_simultaneous_departures(self):
        """Late at night the board rolls into tomorrow, where the village bus
        and the Continental Express both depart at 10:05 — a tie that used to
        make sorted() compare route dicts and crash the transport page."""
        from terra.transit import timetable

        late = timezone.localtime().replace(hour=23, minute=10, second=0,
                                            microsecond=0)
        board = timetable('vermilion', now=late)
        epochs = [row['epoch'] for row in board]
        self.assertEqual(epochs, sorted(epochs))
        self.assertEqual(len(board), 10)
        kinds = {row['kind'] for row in board}
        self.assertEqual(kinds, {'bus', 'train'})
        self.assertTrue(all(row['day_label'] == 'Tomorrow'
                            for row in board))

    # ---- paying fares ----

    def test_pay_fare_decreases_balance_and_issues_qr(self):
        from terra.transit import timetable

        user = self._user(trx='100.000000')
        first = timetable('aurelia')[0]
        traveler = Traveler.objects.get(user=user, relation='self')

        response = self.client.post(reverse('terra:transport'), {
            'action': 'pay',
            'depart': first['value'],
            'traveler_id': traveler.id,
        }, follow=True)
        self.assertRedirects(response, reverse('terra:transport'))

        profile = Profile.objects.get(user=user)
        expected = Decimal('100.000000') - first['fare']
        self.assertEqual(profile.trx_balance, expected)

        # the toast shows the decreasing calculation
        output = [str(m) for m in response.context['messages']]
        self.assertTrue(
            any(str(first['fare']) in m and '=' in m for m in output), output,
        )

        ticket = FareTicket.objects.get(user=user)
        self.assertEqual(ticket.traveler, traveler)
        self.assertEqual(ticket.route_id, first['route'])
        self.assertEqual(ticket.fare_trx, first['fare'])
        self.assertEqual(
            ticket.payload, f'terranova://ticket/{ticket.code}',
        )
        self.assertEqual(ticket.status, 'valid')

        # the QR renders as inline SVG and the ticket is on the page
        svg = ticket.qr_svg
        self.assertIn('<svg', svg)
        self.assertIn('viewBox', svg)
        self.assertGreater(len(svg), 1000)

        page = response.content.decode()
        self.assertIn(ticket.code, page)
        self.assertIn('Show at boarding', page)

        tx = Transaction.objects.get(user=user, kind='fare')
        self.assertEqual(tx.trx, -first['fare'])
        self.assertIn(first['route'], tx.note)

        # balance strip reflects the decrease
        self.assertContains(response, f'{profile.trx_balance:,.6f}')

    def test_child_fare_is_half_price(self):
        from terra.transit import ROUTES_BY_ID, fare_for, timetable

        user = self._user(trx='100.000000')
        child = Traveler.objects.create(user=user, name='Mia', relation='child')
        spouse = Traveler.objects.create(user=user, name='Sam', relation='spouse')
        route = ROUTES_BY_ID['B1']

        self.assertEqual(
            fare_for(route, child), route['fare'] * Decimal('0.5'),
        )
        self.assertEqual(fare_for(route, spouse), route['fare'])

        first = timetable('aurelia')[0]
        self.client.post(reverse('terra:transport'), {
            'action': 'pay',
            'depart': first['value'],
            'traveler_id': child.id,
        }, follow=True)

        ticket = FareTicket.objects.get(user=user)
        self.assertEqual(ticket.traveler.name, 'Mia')
        profile = Profile.objects.get(user=user)
        expected = Decimal('100.000000') - first['fare'] * Decimal('0.5')
        self.assertEqual(profile.trx_balance, expected)
    def test_pay_rejects_bad_selections_and_low_funds(self):
        from terra.transit import timetable

        user = self._user(trx='0.000001')
        traveler = Traveler.objects.get(user=user, relation='self')
        stranger = User.objects.create_user(
            'stranger2', 'stranger2@example.com', 'x-password-9x',
        )
        stranger_traveler = Traveler.objects.create(
            user=stranger, name='Not You', relation='self',
        )

        valid = timetable('aurelia')[0]['value']
        attempts = [
            {'depart': valid, 'traveler_id': traveler.id},        # no funds
            {'depart': 'B1|99999999999', 'traveler_id': traveler.id},  # bad time
            {'depart': 'ZZ|123', 'traveler_id': traveler.id},          # bad route
            {'depart': valid, 'traveler_id': stranger_traveler.id},     # not yours
            {'depart': 'nonsense', 'traveler_id': traveler.id},         # malformed
        ]
        for payload in attempts:
            self.client.post(
                reverse('terra:transport'),
                dict({'action': 'pay'}, **payload), follow=True,
            )
        self.assertEqual(FareTicket.objects.count(), 0)
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.trx_balance, Decimal('0.000001'))
        self.assertEqual(Transaction.objects.filter(kind='fare').count(), 0)

    def test_add_family_member_and_buy_their_fare(self):
        from terra.transit import timetable

        self._user(trx='100.000000')
        self.client.post(reverse('terra:transport'), {
            'action': 'add_traveler',
            'name': 'Mia',
            'relation': 'child',
        }, follow=True)

        child = Traveler.objects.get(user__username='rider', name='Mia')
        response = self.client.get(reverse('terra:transport'))
        self.assertContains(response, 'Mia')
        self.assertContains(response, 'Child · half fare')

        first = timetable('aurelia')[0]
        self.client.post(reverse('terra:transport'), {
            'action': 'pay',
            'depart': first['value'],
            'traveler_id': child.id,
        }, follow=True)
        ticket = FareTicket.objects.get(user__username='rider')
        self.assertEqual(ticket.traveler, child)

    def test_receiver_scan_boards_the_ticket(self):
        from terra.transit import timetable

        user = self._user(trx='100.000000')
        traveler = Traveler.objects.get(user=user, relation='self')
        first = timetable('aurelia')[0]
        self.client.post(reverse('terra:transport'), {
            'action': 'pay',
            'depart': first['value'],
            'traveler_id': traveler.id,
        }, follow=True)
        ticket = FareTicket.objects.get(user=user)

        # a stranger cannot scan your ticket
        stranger = User.objects.create_user(
            'nosyscanner', 'noscanner@example.com', 'x-password-9x',
        )
        self.client.force_login(stranger)
        self.client.post(reverse('terra:transport'), {
            'action': 'scan', 'ticket_id': ticket.id,
        }, follow=True)
        ticket.refresh_from_db()
        self.assertFalse(ticket.used)

        # the owner scans at the receiver → boarded
        self.client.force_login(user)
        response = self.client.post(reverse('terra:transport'), {
            'action': 'scan', 'ticket_id': ticket.id,
        }, follow=True)
        ticket.refresh_from_db()
        self.assertTrue(ticket.used)
        self.assertEqual(ticket.status, 'boarded')
        self.assertContains(response, 'Boarded · scanned')

        # scanning twice is refused politely
        self.client.post(reverse('terra:transport'), {
            'action': 'scan', 'ticket_id': ticket.id,
        }, follow=True)
        ticket.refresh_from_db()
        self.assertTrue(ticket.used)
    # CHAT_TESTS
    # I18N / LANGUAGE SWITCHER TESTS

class I18nLanguageSwitchTests(TestCase):
    """Multi-language support: EN, FR, MG, MFE (Morisien), ZH, RU + selector."""

    def test_switcher_lists_all_six_languages(self):
        home = self.client.get(reverse('terra:home'))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, reverse('set_language'))
        for code in ('en', 'fr', 'mg', 'mfe', 'zh', 'ru'):
            self.assertContains(home, f'<option value="{code}"')

    def test_switch_to_french_sets_cookie_and_translates(self):
        response = self.client.post(
            reverse('set_language'), {'language': 'fr', 'next': '/'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.cookies['django_language'].value, 'fr')
        home = self.client.get('/')
        self.assertContains(home, 'Marché')          # nav: Market
        self.assertContains(home, 'Se connecter')    # nav: Sign in
        self.assertContains(home, 'lang="fr"')       # <html lang="fr">

    def test_nav_translated_in_each_language(self):
        expected = {
            'fr': 'Marché', 'mg': 'Tsena', 'mfe': 'Marché',
            'zh': '市场', 'ru': 'Рынок',
        }
        for code, market in expected.items():
            self.client.post(reverse('set_language'), {'language': code, 'next': '/'})
            home = self.client.get('/')
            self.assertContains(home, market, msg_prefix=f'nav in {code}')

    def test_english_is_default_and_falls_back(self):
        home = self.client.get(reverse('terra:home'))
        self.assertContains(home, '>Market<')
        self.assertContains(home, 'lang="en"')
        self.assertContains(home, 'Sign in')

    def test_form_labels_translate(self):
        from .forms import LoginForm, SignupForm
        with translation.override('ru'):
            self.assertEqual(
                str(LoginForm().fields['username'].label), 'Имя пассажира',
            )
            self.assertEqual(str(LoginForm().fields['password'].label), 'Пароль')
        with translation.override('fr'):
            self.assertEqual(
                str(SignupForm().fields['first_name'].label), 'Nom complet',
            )

    def test_auth_pages_translate(self):
        self.client.post(reverse('set_language'), {'language': 'zh', 'next': '/'})
        login_page = self.client.get(reverse('terra:login'))
        self.assertContains(login_page, '进入任务控制中心')   # Enter Mission Control
        signup_page = self.client.get(reverse('terra:signup'))
        self.assertContains(signup_page, '签发我的通行证')     # Issue my passage

    def test_unsupported_language_does_not_activate(self):
        response = self.client.post(
            reverse('set_language'), {'language': 'zz', 'next': '/'},
        )
        self.assertIn(response.status_code, (302, 400, 406))
        if 'django_language' in response.cookies:
            self.assertNotEqual(response.cookies['django_language'].value, 'zz')


class AdminControlDeckTests(TestCase):
    """Terra Nova admin redesign: dashboard, charts, precise registries."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            'commander', 'commander@terra.earth', 'Passw0rd!2345',
        )
        self.crew = User.objects.create_user(
            'starfarer', 'starfarer@terra.earth', 'Passw0rd!2345',
        )
        self.profile = Profile.objects.create(user=self.crew)
        self.txn = Transaction.objects.create(
            user=self.crew, kind='buy', trx=Decimal('2.500000'),
            usd=Decimal('10.00'), price_usd=Decimal('4.00'), note='deck test',
        )
        self.civic = CivicRequest.objects.create(
            user=self.crew, category='road', sector='aurelia',
            location='Loop 9 interchange',
        )
        self.bill = TaxBill.objects.create(
            user=self.crew, code='FY2026-Q4',
            amount_trx=Decimal('120.000000'),
        )
        self.thread = ChatThread.objects.create(
            user=self.crew, subject='Airlock pressure',
        )
        traveler = Traveler.objects.create(
            user=self.crew, name='Kito', relation='self',
        )
        self.ticket = FareTicket.objects.create(
            user=self.crew, traveler=traveler, route_id='B1',
            route_name='Lagoon Loop', kind='bus',
            destination='Aurelia Dock',
            departure=timezone.now() + timedelta(hours=2),
            fare_trx=Decimal('2.500000'), code='TN-FARE-TEST-1',
        )
        WeatherAlert.objects.create(
            day=timezone.localdate(), severity='high',
            temp_c=Decimal('41.5'), anomaly=Decimal('3.1'),
            headline='Heat spike over Aurelia', message='Drink water.',
        )
        self.client.force_login(self.boss)

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])

    def test_dashboard_renders_kpis_and_charts(self):
        response = self.client.get(reverse('admin:index'))
        self.assertEqual(response.status_code, 200)
        kpis = {k['label']: k['value'] for k in response.context['kpis']}
        self.assertEqual(kpis['NOVARIANS'], '2')
        self.assertEqual(kpis['TRX IN CIRCULATION'], '0.00')
        self.assertEqual(kpis['TERRAX FLOW · 14D'], '1')
        html = response.content.decode()
        self.assertGreaterEqual(html.count('role="img"'), 7)
        for marker in ('Control <em>Deck</em>', 'CREW ADMISSIONS',
                       'HEAT RIBBON', 'SIGNALS · LIVE FEED',
                       'starfarer joined', 'Airlock pressure'):
            self.assertIn(marker, html)

    def test_all_ten_registries_render(self):
        names = [
            'admin:auth_user_changelist',
            'admin:terra_profile_changelist',
            'admin:terra_transaction_changelist',
            'admin:terra_taxbill_changelist',
            'admin:terra_civicrequest_changelist',
            'admin:terra_traveler_changelist',
            'admin:terra_fareticket_changelist',
            'admin:terra_chatthread_changelist',
            'admin:terra_chatmessage_changelist',
            'admin:terra_weatheralert_changelist',
        ]
        for name in names:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_transaction_ledger_is_view_only(self):
        add = self.client.get(reverse('admin:terra_transaction_add'))
        self.assertEqual(add.status_code, 403)
        change = self.client.get(
            reverse('admin:terra_transaction_change', args=[self.txn.pk]),
        )
        self.assertEqual(change.status_code, 200)
        self.assertContains(change, 'deck test')

    def test_ledger_csv_export_action(self):
        response = self.client.post(
            reverse('admin:terra_transaction_changelist'),
            {'action': 'export_csv', '_selected_action': [str(self.txn.pk)]},
        )
        self.assertEqual(response['Content-Type'], 'text/csv')
        body = response.content.decode()
        self.assertIn('deck test', body)
        self.assertIn('starfarer', body)

    def test_civic_stage_filter_runs_in_sql(self):
        url = reverse('admin:terra_civicrequest_changelist')
        tracking = f'GR-{self.civic.pk:04d}'
        fresh = self.client.get(url + '?stage=received')
        self.assertEqual(fresh.status_code, 200)
        self.assertContains(fresh, tracking)
        old = self.client.get(url + '?stage=scheduled')
        self.assertEqual(old.status_code, 200)
        self.assertNotContains(old, tracking)

    def test_fare_boarding_filter_and_scan_action(self):
        url = reverse('admin:terra_fareticket_changelist')
        valid = self.client.get(url + '?bstate=valid')
        self.assertContains(valid, 'TN-FARE-TE')
        self.client.post(
            url,
            {'action': 'mark_boarded', '_selected_action': [str(self.ticket.pk)]},
            follow=True,
        )
        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.used)

    def test_taxbill_mark_paid_action(self):
        self.client.post(
            reverse('admin:terra_taxbill_changelist'),
            {'action': 'mark_paid', '_selected_action': [str(self.bill.pk)]},
            follow=True,
        )
        self.bill.refresh_from_db()
        self.assertEqual(self.bill.status, 'paid')
        self.assertIsNotNone(self.bill.paid_at)

    def test_chart_helpers_emit_accessible_svg(self):
        from .charts import (
            area_chart, donut, hbars, sparkline, weather_ribbon,
        )
        area = area_chart(['10-01', '10-02'], [1, 3], 'Test chart')
        self.assertIn('<svg', area)
        self.assertIn('role="img"', area)
        self.assertIn('<title>', area)
        ring = donut([('A', 3, '#fff'), ('B', 1, '#000')], '4', 'TOTAL')
        self.assertIn('stroke-dasharray', ring)
        bars = hbars([('X', 2, '#fff')], 'Bars')
        self.assertIn('<rect', bars)
        ribbon = weather_ribbon(
            [{'label': 'Fri 03', 'temp': 41.6, 'severity': 'extreme',
              'anomaly': '+3.1°C'}],
            'Ribbon',
        )
        self.assertIn('Fri 03', ribbon)
        self.assertIn('polyline', sparkline([1, 2, 3], label='t'))

    def test_admin_is_themed_and_branded(self):
        self.client.logout()
        login_page = self.client.get('/admin/login/')
        self.assertContains(login_page, 'Terra Nova')
        self.assertContains(login_page, 'css/admin.css')
        self.client.force_login(self.boss)
        deck = self.client.get(reverse('admin:index'))
        self.assertContains(deck, 'css/admin.css')
        self.assertContains(deck, 'MISSION CONTROL')


class AdminLoginPageTests(TestCase):
    """Redesigned login: the airlock gate — layout + working auth flow."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            'deckmaster', 'deck@terra.earth', 'GatePass2345',
        )

    def test_login_redesign_layout(self):
        response = self.client.get('/admin/login/')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in (
            'tn-login__art', 'Mission <em>Control</em>', 'CREW ACCESS',
            'Enter Control Deck', 'id="login-form"', 'name="next"',
            'tn-login__orb', 'Back to Terra Nova surface', 'tn-login__facts',
        ):
            self.assertIn(marker, html)
        # stock admin login stylesheet is superseded by the deck theme
        self.assertNotContains(response, 'admin/css/login.css')

    def test_login_flow_still_works(self):
        response = self.client.post(
            '/admin/login/',
            {'username': 'deckmaster', 'password': 'GatePass2345',
             'next': '/admin/'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/admin/')
        deck = self.client.get('/admin/')
        self.assertContains(deck, 'Control <em>Deck</em>')

    def test_bad_credentials_show_styled_error(self):
        response = self.client.post(
            '/admin/login/',
            {'username': 'deckmaster', 'password': 'wrong-gate'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'errornote')
        self.assertContains(response, 'tn-login__panel')


class AdminInterfaceOverhaulTests(TestCase):
    """UI/UX overhaul: changelist chrome, filter chips, forms, pagination."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            'ui_captain', 'ui@terra.earth', 'Overhaul2345',
        )
        crew = User.objects.create_user('passenger1', 'p1@terra.earth', 'x')
        self.civic = CivicRequest.objects.create(
            user=crew, category='road', sector='aurelia', location='Deck 4',
        )
        self.client.force_login(self.boss)

    def test_changelist_header_toolbar_and_pagination(self):
        response = self.client.get(
            reverse('admin:terra_civicrequest_changelist'),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in (
            'tn-eyebrow', 'tn-cl-title', 'tn-pill', 'tn-toolbar', 'tn-search',
            'tn-kbd', 'id="searchbar"', 'tn-paginator', 'tn-page-summary',
            'js/admin.js', 'object-tools', 'changelist-filter',
        ):
            self.assertIn(marker, html)

    def test_active_filter_chips_render_and_drop_param(self):
        url = reverse('admin:terra_civicrequest_changelist')
        response = self.client.get(url + '?stage=received')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('tn-active__chip', html)
        self.assertIn('tn-active__clear', html)
        # the chip's own href must not carry the parameter it removes
        block = html[html.index('class="tn-active"'): html.index('</div>', html.index('class="tn-active"'))]
        self.assertNotIn('stage=', block)
        # filtering still works alongside the new chrome
        self.assertContains(response, f'GR-{self.civic.pk:04d}')

    def test_change_form_meta_strip_and_sticky_bar(self):
        response = self.client.get(
            reverse('admin:terra_civicrequest_change', args=[self.civic.pk]),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('tn-form-meta', html)
        self.assertIn(f'#{self.civic.pk}', html)
        self.assertIn('t-chip--ice', html)
        self.assertIn('submit-row', html)
        self.assertIn('deletelink', html)

    def test_pagination_summary_is_precise(self):
        response = self.client.get(
            reverse('admin:terra_civicrequest_changelist'),
        )
        self.assertContains(response, 'tn-page-summary')
        self.assertContains(response, '<b>1</b> civic requests', html=True)

    def test_search_shortcut_script_loaded_and_written(self):
        response = self.client.get(
            reverse('admin:terra_profile_changelist'),
        )
        self.assertContains(response, 'js/admin.js')
        js = (Path(settings.BASE_DIR) / 'static' / 'js' / 'admin.js').read_text()
        self.assertIn("keydown", js)
        self.assertIn("'/'", js)




class SecurityWatchTests(TestCase):
    """Device limit + attack detection → email and notification centre."""

    def setUp(self):
        self.user = User.objects.create_user(
            'nova', 'nova@terra.earth', 'SecretPass2345',
        )

    def _login(self, ua, password='SecretPass2345', username='nova'):
        return self.client.post(
            reverse('terra:login'),
            {'username': username, 'password': password},
            HTTP_USER_AGENT=ua,
        )

    # -- device limit ------------------------------------------------

    def test_two_devices_stay_silent(self):
        self._login('DeviceOne/1.0')
        self.client.logout()
        self._login('DeviceTwo/2.0')
        self.assertEqual(DeviceLogin.objects.count(), 2)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_third_device_alerts_by_email_and_notification(self):
        self._login('DeviceOne/1.0')
        self.client.logout()
        self._login('DeviceTwo/2.0')
        self.client.logout()
        response = self._login('DeviceThree/3.0')
        self.assertEqual(response.status_code, 302)

        self.assertEqual(DeviceLogin.objects.count(), 3)
        note = Notification.objects.get()
        self.assertEqual(note.kind, 'device')
        self.assertEqual(note.user, self.user)
        self.assertFalse(note.is_read)
        self.assertTrue(note.emailed)
        self.assertEqual(note.link, '/notifications/')
        self.assertIn('3 active devices', note.body)
        self.assertIn('DeviceThree/3.0', note.body)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['nova@terra.earth'])
        self.assertIn('[Terra Nova]', message.subject)
        self.assertIn('device #3', message.subject)

    def test_same_device_relogin_does_not_realert(self):
        self._login('DeviceOne/1.0')
        self.client.logout()
        self._login('DeviceTwo/2.0')
        self.client.logout()
        self._login('DeviceThree/3.0')
        self.client.logout()
        self._login('DeviceThree/3.0')
        self.assertEqual(DeviceLogin.objects.count(), 3)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_mail_failure_never_breaks_login(self):
        self._login('DeviceOne/1.0')
        self.client.logout()
        self._login('DeviceTwo/2.0')
        self.client.logout()
        with patch(
            'terra.security.send_mail', side_effect=OSError('smtp down'),
        ):
            response = self._login('DeviceThree/3.0')
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('terra:dashboard'))
        note = Notification.objects.get()
        self.assertEqual(note.kind, 'device')
        self.assertFalse(note.emailed)

    # -- attack detection ---------------------------------------------

    def test_attack_alert_at_fifth_failed_sign_in(self):
        for _ in range(4):
            response = self._login('AttackerBox/9.0', password='wrong-guess')
            self.assertEqual(response.status_code, 200)  # form error shown
        self.assertEqual(LoginAttempt.objects.count(), 4)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

        self._login('AttackerBox/9.0', password='wrong-guess')
        self.assertEqual(LoginAttempt.objects.count(), 5)
        note = Notification.objects.get()
        self.assertEqual(note.kind, 'security')
        self.assertIn('5 failed sign-ins', note.title)
        self.assertIn('Addresses seen: 127.0.0.1', note.body)
        self.assertTrue(note.emailed)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Possible attack', mail.outbox[0].subject)

        # still inside the window → no duplicate alert
        self._login('AttackerBox/9.0', password='wrong-guess')
        self.assertEqual(LoginAttempt.objects.count(), 6)
        self.assertEqual(Notification.objects.count(), 1)

    def test_unknown_username_attempts_are_logged_silently(self):
        for _ in range(5):
            self._login('GhostProbe/1.0', username='ghost',
                        password='wrong-guess')
        self.assertEqual(LoginAttempt.objects.count(), 5)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_login_is_not_counted_as_attack(self):
        self._login('GoodDevice/1.0')
        self.client.logout()
        self._login('GoodDevice/1.0')
        self.client.logout()
        self._login('GoodDevice/1.0', password='wrong-guess')
        self.assertEqual(LoginAttempt.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)

    # -- notification centre -------------------------------------------

    def test_notification_centre_requires_login(self):
        response = self.client.get(reverse('terra:notifications'))
        self.assertRedirects(
            response,
            f"{reverse('terra:login')}?next={reverse('terra:notifications')}",
        )

    def test_notification_centre_renders_and_marks_all_read(self):
        Notification.objects.create(
            user=self.user, kind='security',
            title='Possible attack: 5 failed sign-ins in 10 minutes',
            body='Someone is guessing your passphrase.',
        )
        Notification.objects.create(
            user=self.user, kind='device',
            title='Sign-in from device #3 — limit is 2',
            body='A new device just signed in.',
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('terra:notifications'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in (
            'nc__title', 'nc__item--security', 'nc__item--device',
            'nc__list', 'nc__devices', 'YOUR DEVICES',
            'Sign out all other sessions',
        ):
            self.assertIn(marker, html)
        self.assertIn('2 unread', html)

        posted = self.client.post(
            reverse('terra:notifications'), {'action': 'mark_all'},
        )
        self.assertEqual(posted.status_code, 302)
        self.assertFalse(
            Notification.objects.filter(user=self.user, is_read=False).exists(),
        )

    def test_single_notification_acknowledge(self):
        note = Notification.objects.create(
            user=self.user, kind='info', title='Welcome aboard',
            body='First signal.',
        )
        self.client.force_login(self.user)
        self.client.post(
            reverse('terra:notifications'),
            {'action': 'mark', 'id': note.pk},
        )
        note.refresh_from_db()
        self.assertTrue(note.is_read)

    def test_nav_bell_counts_unread(self):
        Notification.objects.create(
            user=self.user, kind='device', title='One', body='b',
        )
        Notification.objects.create(
            user=self.user, kind='security', title='Two', body='b',
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('terra:dashboard'))
        self.assertContains(response, 'nav__bell')
        self.assertContains(response, 'nav__bell-count')
        html = response.content.decode()
        badge = re.search(r'nav__bell-count[^>]*>\s*(\d+)\s*<', html)
        self.assertIsNotNone(badge, 'unread badge missing from nav')
        self.assertEqual(badge.group(1), '2')

    def test_nav_bell_hidden_for_anonymous(self):
        response = self.client.get(reverse('terra:home'))
        self.assertNotContains(response, 'nav__bell')

    def test_security_models_registered_in_control_deck(self):
        boss = User.objects.create_superuser(
            'sec_admin', 'sec@terra.earth', 'DeckPass2345',
        )
        self.client.force_login(boss)
        for name in (
            'admin:terra_devicelogin_changelist',
            'admin:terra_loginattempt_changelist',
            'admin:terra_notification_changelist',
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)


class AccountCentreTests(TestCase):
    """Account page: profile edits, avatar, PDF dossier, agent ratings."""

    def setUp(self):
        self.user = User.objects.create_user(
            'pathfinder', 'pf@terra.earth', 'TrailPass2345',
            first_name='Path Finder',
        )
        self.profile = Profile.objects.create(user=self.user)
        self.client.force_login(self.user)

    # -- page ----------------------------------------------------------

    def test_account_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('terra:account'))
        self.assertRedirects(
            response,
            f"{reverse('terra:login')}?next={reverse('terra:account')}",
        )

    def test_account_renders_all_sections(self):
        response = self.client.get(reverse('terra:account'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in (
            'ac__title', 'Account', 'centre.', 'id="profile"', 'id="photo"',
            'id="ratings"', 'id="dossier"', 'Identity record',
            'Passenger photo', 'Rate a Novarian agent', 'Passenger dossier',
            'Download dossier (PDF)', 'name="action" value="profile"',
            'type="file"', 'nav__bell',
        ):
            self.assertIn(marker, html)

    def test_nav_account_icon_present_when_authenticated(self):
        response = self.client.get(reverse('terra:dashboard'))
        self.assertContains(response, '/account/')

    def test_nav_account_icon_hidden_for_anonymous(self):
        self.client.logout()
        response = self.client.get(reverse('terra:home'))
        self.assertNotContains(response, '/account/')


    # -- profile update ------------------------------------------------

    def test_profile_update_saves_identity(self):
        response = self.client.post(
            reverse('terra:account'),
            {
                'action': 'profile',
                'first_name': 'Renamed Voyager',
                'email': 'renamed@terra.earth',
                'tagline': 'Updated from the account centre.',
                'sector': 'pelagos',
                'date_of_birth': '1990-04-12',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Renamed Voyager')
        self.assertEqual(self.user.email, 'renamed@terra.earth')
        self.assertEqual(self.profile.tagline, 'Updated from the account centre.')
        self.assertEqual(self.profile.sector, 'pelagos')
        self.assertEqual(
            self.profile.date_of_birth.isoformat(), '1990-04-12',
        )
        self.assertContains(response, 'Passenger record updated.')

    def test_profile_update_rejects_duplicate_email(self):
        User.objects.create_user('taken', 'taken@terra.earth', 'x-pass12345')
        self.client.post(
            reverse('terra:account'),
            {
                'action': 'profile',
                'first_name': 'Path Finder',
                'email': 'taken@terra.earth',
                'tagline': '',
                'sector': 'aurelia',
                'date_of_birth': '',
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'pf@terra.earth')  # unchanged

    def test_profile_update_allows_own_email(self):
        self.client.post(
            reverse('terra:account'),
            {
                'action': 'profile',
                'first_name': 'Path Finder',
                'email': 'pf@terra.earth',
                'tagline': 'same email ok',
                'sector': 'aurelia',
                'date_of_birth': '',
            },
        )
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.tagline, 'same email ok')

    def test_future_date_of_birth_rejected(self):
        self.client.post(
            reverse('terra:account'),
            {
                'action': 'profile',
                'first_name': 'Path Finder',
                'email': 'pf@terra.earth',
                'tagline': '',
                'sector': 'aurelia',
                'date_of_birth': '2999-01-01',
            },
        )
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.date_of_birth)

    # -- avatar ----------------------------------------------------------

    def _png_bytes(self, size=(120, 120), color=(255, 178, 87)):
        import io

        from PIL import Image

        buf = io.BytesIO()
        Image.new('RGB', size, color).save(buf, format='PNG')
        return buf.getvalue()

    def test_avatar_upload_scales_and_stores(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            'portrait.png', self._png_bytes(size=(900, 700)),
            content_type='image/png',
        )
        response = self.client.post(
            reverse('terra:account'),
            {'action': 'avatar', 'avatar': upload},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.avatar)
        self.assertContains(response, 'Passenger photo updated.')

        # downscaled to fit 640 px and re-encoded as JPEG
        from PIL import Image

        with self.profile.avatar.open('rb') as fh:
            img = Image.open(fh)
            self.assertEqual(img.format, 'JPEG')
            self.assertLessEqual(max(img.size), 640)
        # the page shows the uploaded picture
        self.assertContains(response, self.profile.avatar.url)

    def test_avatar_rejects_oversize_and_garbage(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        big = SimpleUploadedFile(
            'big.png', self._png_bytes() + b'\x00' * (2 * 1024 * 1024),
            content_type='image/png',
        )
        self.client.post(
            reverse('terra:account'), {'action': 'avatar', 'avatar': big},
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

        junk = SimpleUploadedFile(
            'junk.png', b'not an image at all', content_type='image/png',
        )
        self.client.post(
            reverse('terra:account'), {'action': 'avatar', 'avatar': junk},
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    def test_avatar_clear_removes_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile(
            'portrait.png', self._png_bytes(), content_type='image/png',
        )
        self.client.post(
            reverse('terra:account'), {'action': 'avatar', 'avatar': upload},
        )
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.avatar)
        self.client.post(
            reverse('terra:account'), {'action': 'avatar_clear'},
        )
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)


    # -- PDF dossier ------------------------------------------------------

    def test_dossier_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse('terra:account_pdf'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])

    def test_dossier_downloads_as_valid_pdf(self):
        Transaction.objects.create(
            user=self.user, kind='buy', trx=Decimal('4.000000'),
            usd=Decimal('15.00'), price_usd=Decimal('3.75'),
            note='dossier probe',
        )
        response = self.client.get(reverse('terra:account_pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn(
            'attachment', response['Content-Disposition'],
        )
        self.assertIn('pathfinder', response['Content-Disposition'])
        data = response.content
        self.assertTrue(data.startswith(b'%PDF-1.4'))
        self.assertTrue(data.rstrip().endswith(b'%%EOF'))

        # structural integrity: startxref resolves, every offset is right
        import re

        match = re.search(rb'startxref\n(\d+)\n%%EOF', data)
        self.assertIsNotNone(match)
        xref = int(match.group(1))
        self.assertEqual(data[xref:xref + 4], b'xref')
        entries = re.findall(rb'(\d{10}) \d{5} n', data[xref:])
        self.assertGreater(len(entries), 5)
        for i, off in enumerate(entries, start=1):
            pos = int(off)
            self.assertEqual(
                data[pos:pos + len(f'{i} 0 obj') + 1],
                f'{i} 0 obj\n'.encode(),
                f'object {i} offset broken',
            )

        # content: identity, ledger note, section headings (headings print
        # uppercased by the PDF writer)
        for marker in (
            b'Passenger dossier', b'pathfinder', b'IDENTITY RECORD',
            b'WALLET & CLEARANCE', b'TERRAX LEDGER', b'dossier probe',
            b'SECURITY WATCH', b'STATEMENT',
        ):
            self.assertIn(marker, data)

    def test_dossier_contains_civic_and_rating_records(self):
        from .dossier import build_dossier

        CivicRequest.objects.create(
            user=self.user, category='road', sector='aurelia',
            location='Lighthouse ridge',
        )
        agent = User.objects.create_user(
            'relay_star', 'relay@terra.earth', 'RelayPass2345',
        )
        AgentRating.objects.create(
            user=self.user, agent=agent, rating=4,
            comment='Cleared my signal fast.',
        )
        data = build_dossier(self.user)
        for marker in (
            b'GR-', b'Lighthouse ridge', b'AGENT RATINGS',
            b'relay_star', b'Cleared my signal fast.',
        ):
            self.assertIn(marker, data)

    def test_dossier_handles_sparse_account(self):
        from .dossier import build_dossier

        sparse = User.objects.create_user(
            'bare_hull', 'bare@terra.earth', 'BarePass2345',
        )
        Profile.objects.create(user=sparse)
        data = build_dossier(sparse)
        self.assertTrue(data.startswith(b'%PDF-1.4'))
        self.assertIn(b'bare_hull', data)

    # -- agent ratings -----------------------------------------------------

    def test_rating_requires_login(self):
        self.client.logout()
        response = self.client.post(reverse('terra:account'), {
            'action': 'rate', 'agent': 1, 'rating': 5,
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('next=', response['Location'])


    def _make_agent(self, username='relay_star'):
        agent = User.objects.create_user(
            username, f'{username}@terra.earth', 'AgentPass2345',
        )
        Profile.objects.create(user=agent, is_agent=True)
        return agent

    def test_rate_agent_creates_rating(self):
        agent = self._make_agent()
        response = self.client.post(
            reverse('terra:account'),
            {
                'action': 'rate', 'agent': agent.pk, 'rating': '5',
                'comment': 'Fast, kind, precise.',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rating saved')
        rating = AgentRating.objects.get(user=self.user, agent=agent)
        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.comment, 'Fast, kind, precise.')

    def test_rating_updates_existing_row(self):
        agent = self._make_agent()
        for stars, comment in ((3, 'ok'), (5, 'outstanding')):
            self.client.post(
                reverse('terra:account'),
                {
                    'action': 'rate', 'agent': agent.pk,
                    'rating': str(stars), 'comment': comment,
                },
            )
        self.assertEqual(
            AgentRating.objects.filter(user=self.user).count(), 1,
        )
        rating = AgentRating.objects.get(user=self.user, agent=agent)
        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.comment, 'outstanding')

    def test_rating_out_of_range_rejected(self):
        agent = self._make_agent()
        self.client.post(
            reverse('terra:account'),
            {'action': 'rate', 'agent': agent.pk, 'rating': '9'},
        )
        self.assertFalse(
            AgentRating.objects.filter(user=self.user).exists(),
        )

    def test_rating_unknown_agent_rejected(self):
        self.client.post(
            reverse('terra:account'),
            {'action': 'rate', 'agent': 9999, 'rating': '5'},
        )
        self.assertFalse(
            AgentRating.objects.filter(user=self.user).exists(),
        )

    def test_account_lists_agents_and_previous_rating(self):
        agent = self._make_agent(username='stellar_hand')
        AgentRating.objects.create(
            user=self.user, agent=agent, rating=4, comment='solid work',
        )
        response = self.client.get(reverse('terra:account'))
        html = response.content.decode()
        self.assertIn('stellar_hand', html)
        self.assertIn('solid work', html)
        self.assertIn('ac__agents', html)
        # the 4th radio must be checked for a 4★ rating
        self.assertIn('checked', html)

    def test_met_badge_shows_for_assigned_agent(self):
        agent = self._make_agent('assigned_one')
        thread = ChatThread.objects.create(
            user=self.user, subject='Broken airlock',
            assigned_agent=agent, status='escalated',
        )
        self.assertIsNotNone(thread.assigned_agent)
        response = self.client.get(reverse('terra:account'))
        self.assertContains(response, 'MET')

    def test_agent_rating_registered_in_control_deck(self):
        boss = User.objects.create_superuser(
            'rate_admin', 'rate@terra.earth', 'DeckPass2345',
        )
        self.client.force_login(boss)
        response = self.client.get(
            reverse('admin:terra_agentrating_changelist'),
        )
        self.assertEqual(response.status_code, 200)



class ConnectivityTests(TestCase):
    """Low-bandwidth tiers: net.js detection, cookie gating, SW cache."""

    def test_net_js_detects_512k_and_1m_tiers(self):
        js = Path(settings.BASE_DIR, 'static', 'js', 'net.js').read_text()
        for marker in (
            'navigator.connection', 'downlink', 'saveData',
            'slow-2g', 'tn_net', 'terra:net', 'data-net-tier',
            '0.5',                      # 512 kbps boundary
            'icon-192x192.png',         # probe fallback (no connection API)
            "'balanced'", 'offline', 'online', 'max-age=2592000',
        ):
            self.assertIn(marker, js)

    def test_net_tier_context_processor_defaults_to_full(self):
        resp = self.client.get(reverse('terra:home'))
        self.assertEqual(resp.context['net_tier'], 'full')

        self.client.cookies['tn_net'] = 'lite'
        resp = self.client.get(reverse('terra:home'))
        self.assertEqual(resp.context['net_tier'], 'lite')

        self.client.cookies['tn_net'] = 'nonsense'
        resp = self.client.get(reverse('terra:home'))
        self.assertEqual(resp.context['net_tier'], 'full')

    def test_lite_cookie_serves_essential_only_dashboard(self):
        user = User.objects.create_user('litech', 'lc@terra.earth', 'pw12345!')
        Profile.objects.create(user=user)
        self.client.force_login(user)

        full = self.client.get(reverse('terra:dashboard')).content.decode()
        self.assertIn('id="starfield"', full)
        self.assertIn('class="grain"', full)
        self.assertIn('card--crew', full)
        self.assertIn('card--telemetry', full)

        self.client.cookies['tn_net'] = 'lite'
        lite = self.client.get(reverse('terra:dashboard')).content.decode()
        self.assertNotIn('id="starfield"', lite)
        self.assertNotIn('class="grain"', lite)
        self.assertNotIn('card--crew', lite)
        self.assertNotIn('card--telemetry', lite)
        # essential information survives
        self.assertIn('card--wallet', lite)
        self.assertIn('card--sector', lite)

    def test_map_has_lite_render_mode(self):
        js = Path(settings.BASE_DIR, 'static', 'js', 'map.js').read_text()
        for marker in ('tn_net', 'terra:net', 'GRID_LITE', 'setTier'):
            self.assertIn(marker, js)

    def test_weather_polling_is_tier_aware(self):
        js = Path(settings.BASE_DIR, 'static', 'js', 'weather.js').read_text()
        self.assertIn('data-net-tier', js)
        self.assertIn('terra:net', js)
        self.assertIn('setInterval', js)   # full links still poll every 30s

    def test_base_html_bootstraps_tier_from_cookie(self):
        html = Path(settings.BASE_DIR, 'templates', 'base.html').read_text()
        for marker in ('tn_net', 'data-net-tier', 'js/net.js'):
            self.assertIn(marker, html)

    def test_service_worker_v3_precaches_core_and_offers_api_fallback(self):
        sw = Path(settings.BASE_DIR, 'serviceworker.js').read_text()
        self.assertIn("VERSION = 'v3'", sw)
        for marker in (
            '/static/js/net.js', '/static/css/map.css', '/static/js/map.js',
            '/weather/api/', 'networkFirstApi', 'cacheFirst',
            '/offline/', 'staleWhileRevalidate',
        ):
            self.assertIn(marker, sw)


