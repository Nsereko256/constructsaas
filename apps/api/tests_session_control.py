from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, User


class SingleDeviceSessionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Session Test Company')
        self.user = User.objects.create_user(
            username='single-device-user', password='secure-password',
            company=self.company, role=User.ROLE_SITE_ENGINEER,
        )

    def test_new_device_must_confirm_before_ending_existing_session(self):
        first = self.client.post('/api/token/', {'username': self.user.username, 'password': 'secure-password'}, format='json')
        self.assertEqual(first.status_code, 200)

        blocked = self.client.post('/api/token/', {'username': self.user.username, 'password': 'secure-password'}, format='json')
        self.assertEqual(blocked.status_code, 409)

        takeover = self.client.post('/api/token/', {
            'username': self.user.username,
            'password': 'secure-password',
            'terminate_other_session': True,
        }, format='json')
        self.assertEqual(takeover.status_code, 200)

        old_device = APIClient()
        old_device.credentials(HTTP_AUTHORIZATION=f'Bearer {first.data["access"]}')
        self.assertIn(old_device.get('/api/dashboard/').status_code, {401, 403})

        new_device = APIClient()
        new_device.credentials(HTTP_AUTHORIZATION=f'Bearer {takeover.data["access"]}')
        self.assertEqual(new_device.get('/api/dashboard/').status_code, 200)

    def test_same_browser_can_sign_in_again_without_false_device_conflict(self):
        credentials = {
            'username': self.user.username,
            'password': 'secure-password',
            'device_id': 'browser-installation-1',
        }
        first = self.client.post('/api/token/', credentials, format='json')
        self.assertEqual(first.status_code, 200)

        second = self.client.post('/api/token/', credentials, format='json')
        self.assertEqual(second.status_code, 200)

        original_tab = APIClient()
        original_tab.credentials(HTTP_AUTHORIZATION=f'Bearer {first.data["access"]}')
        self.assertEqual(original_tab.get('/api/dashboard/').status_code, 200)
        original_refresh = self.client.post(
            '/api/token/refresh/',
            {'refresh': first.data['refresh']},
            format='json',
        )
        self.assertEqual(original_refresh.status_code, 200)

    def test_inactive_session_marker_does_not_block_a_new_login(self):
        first = self.client.post(
            '/api/token/',
            {'username': self.user.username, 'password': 'secure-password'},
            format='json',
        )
        self.assertEqual(first.status_code, 200)
        type(self.user).objects.filter(pk=self.user.pk).update(
            active_session_started_at=timezone.now() - timedelta(minutes=6),
        )

        replacement = self.client.post(
            '/api/token/',
            {'username': self.user.username, 'password': 'secure-password'},
            format='json',
        )
        self.assertEqual(replacement.status_code, 200)

    def test_authenticated_requests_keep_the_session_marker_current(self):
        login = self.client.post(
            '/api/token/',
            {
                'username': self.user.username,
                'password': 'secure-password',
                'device_id': 'browser-installation-1',
            },
            format='json',
        )
        stale_time = timezone.now() - timedelta(minutes=2)
        type(self.user).objects.filter(pk=self.user.pk).update(active_session_started_at=stale_time)

        active_client = APIClient()
        active_client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        self.assertEqual(active_client.get('/api/dashboard/').status_code, 200)
        self.user.refresh_from_db()
        self.assertGreater(self.user.active_session_started_at, stale_time)
