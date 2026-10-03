from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


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
