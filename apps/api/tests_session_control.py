from django.test import TestCase
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
