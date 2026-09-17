from unittest.mock import patch

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Company, User

from .email_services import email_delivery_status, queue_notification_email
from .helpers import send_notification
from .models import EmailDelivery, EmailNotificationPreference, Notification


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='alerts@example.com',
    FRONTEND_BASE_URL='https://app.example.com',
)
class EmailNotificationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Email Test Construction')
        self.user = User.objects.create_user(
            username='manager', password='password', email='manager@example.com',
            company=self.company, role=User.ROLE_PROJECT_MANAGER,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_notification(self, kind, level=Notification.LEVEL_INFO):
        return Notification.objects.create(
            company=self.company,
            recipient=self.user,
            notification_type=kind,
            level=level,
            title='Review required',
            message='A record is waiting for your decision.',
            link='/procurement/requests/12/',
        )

    def test_required_only_is_the_default_and_queues_action_email(self):
        notification = self.create_notification(Notification.TYPE_PR_SUBMITTED)

        delivery = queue_notification_email(notification)

        preference = EmailNotificationPreference.objects.get(user=self.user)
        self.assertTrue(preference.enabled)
        self.assertTrue(preference.required_only)
        self.assertEqual(delivery.status, EmailDelivery.STATUS_PENDING)
        self.assertEqual(delivery.recipient_email, self.user.email)
        self.assertIn('Action required:', delivery.subject)
        self.assertIn('https://app.example.com/procurement/requests/12/', delivery.text_body)

    def test_routine_update_stays_in_app_until_user_broadens_preference(self):
        notification = self.create_notification(Notification.TYPE_PO_RECEIVED)
        preference = EmailNotificationPreference.objects.create(company=self.company, user=self.user)

        self.assertIsNone(queue_notification_email(notification))
        preference.required_only = False
        preference.save(update_fields=['required_only', 'updated_at'])

        self.assertIsNotNone(queue_notification_email(notification))

    def test_disabled_category_is_respected(self):
        notification = self.create_notification(Notification.TYPE_PR_SUBMITTED)
        EmailNotificationPreference.objects.create(
            company=self.company, user=self.user, procurement=False,
        )

        self.assertIsNone(queue_notification_email(notification))

    def test_outbox_command_sends_queued_email(self):
        delivery = queue_notification_email(self.create_notification(Notification.TYPE_PR_SUBMITTED))

        call_command('process_email_outbox')

        delivery.refresh_from_db()
        self.assertEqual(delivery.status, EmailDelivery.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])

    def test_email_queue_failure_does_not_undo_in_app_notification(self):
        with patch('apps.notifications.email_services.queue_notification_email', side_effect=RuntimeError('provider down')):
            with self.captureOnCommitCallbacks(execute=True):
                notification = send_notification(
                    self.user,
                    Notification.TYPE_PR_SUBMITTED,
                    Notification.LEVEL_WARNING,
                    'Approval needed',
                    'Please review this request.',
                    '/procurement/requests/15/',
                )

        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())

    def test_user_can_read_and_update_selective_preferences(self):
        response = self.client.get('/api/notifications/email-preferences/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['required_only'])
        self.assertFalse(response.data['system'])
        self.assertEqual(response.data['delivery_mode'], 'test')
        self.assertFalse(response.data['real_delivery'])
        self.assertEqual(response.data['pending_count'], 0)

        response = self.client.patch(
            '/api/notifications/email-preferences/',
            {'finance': False, 'required_only': True},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['finance'])
        self.assertTrue(response.data['required_only'])

    def test_test_transport_is_reported_as_preview_instead_of_real_delivery(self):
        response = self.client.post('/api/notifications/send-test-email/', {}, format='json')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['sent'])
        self.assertTrue(response.data['previewed'])
        self.assertEqual(response.data['delivery_mode'], 'test')
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
        EMAIL_HOST='',
        EMAIL_HOST_USER='',
        EMAIL_HOST_PASSWORD='',
    )
    def test_incomplete_smtp_configuration_is_not_reported_ready(self):
        status = email_delivery_status()

        self.assertEqual(status['mode'], 'unconfigured')
        self.assertFalse(status['configured'])
        self.assertFalse(status['real_delivery'])

    @override_settings(EMAIL_NOTIFICATION_SEND_INLINE=True)
    def test_inline_delivery_sends_new_action_email_and_keeps_outbox_record(self):
        with self.captureOnCommitCallbacks(execute=True):
            notification = send_notification(
                self.user,
                Notification.TYPE_PR_SUBMITTED,
                Notification.LEVEL_WARNING,
                'Approval needed now',
                'Please review this request.',
                '/procurement/requests/18/',
            )

        delivery = EmailDelivery.objects.get(notification=notification)
        self.assertEqual(delivery.status, EmailDelivery.STATUS_SENT)
        self.assertEqual(delivery.attempts, 1)
        self.assertEqual(len(mail.outbox), 1)
