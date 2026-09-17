import re
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailDelivery, EmailNotificationPreference, Notification


REQUIRED_NOTIFICATION_TYPES = {
    Notification.TYPE_LOW_STOCK,
    Notification.TYPE_PR_SUBMITTED,
    Notification.TYPE_PR_REJECTED,
    Notification.TYPE_BUDGET_APPROVAL_REQUIRED,
    Notification.TYPE_BUDGET_THRESHOLD_REACHED,
    Notification.TYPE_PO_EXCEEDING_BUDGET,
    Notification.TYPE_INVOICE_SUBMITTED,
    Notification.TYPE_INVOICE_MATCH_EXCEPTION,
    Notification.TYPE_INVOICE_DUE_SOON,
    Notification.TYPE_INVOICE_OVERDUE,
    Notification.TYPE_PAYMENT_AWAITING_APPROVAL,
    Notification.TYPE_PAYMENT_REJECTED,
    Notification.TYPE_STAFF_ADVANCE_OVERDUE,
    Notification.TYPE_VALUATION_ADJUSTMENT,
    Notification.TYPE_JOURNAL_POSTING_FAILURE,
}


def notification_category(notification):
    kind = notification.notification_type
    link = (notification.link or '').lower()
    if kind.startswith(('pr_', 'po_')) or '/procurement/' in link:
        return 'procurement'
    if kind in {Notification.TYPE_LOW_STOCK, Notification.TYPE_VALUATION_ADJUSTMENT} or '/inventory' in link:
        return 'inventory'
    if kind.startswith('budget_') or '/projects' in link:
        return 'projects'
    if (
        kind.startswith(('invoice_', 'payment_'))
        or kind in {Notification.TYPE_STAFF_ADVANCE_OVERDUE, Notification.TYPE_JOURNAL_POSTING_FAILURE}
        or '/finance/' in link
    ):
        return 'finance'
    return 'system'


def notification_requires_action(notification):
    return (
        notification.level in {Notification.LEVEL_WARNING, Notification.LEVEL_DANGER}
        or notification.notification_type in REQUIRED_NOTIFICATION_TYPES
    )


def email_delivery_mode():
    backend = settings.EMAIL_BACKEND
    if backend.endswith('console.EmailBackend'):
        return 'preview'
    if backend.endswith(('locmem.EmailBackend', 'dummy.EmailBackend')):
        return 'test'
    if backend.endswith('smtp.EmailBackend'):
        return 'smtp' if all((
            settings.EMAIL_HOST,
            settings.EMAIL_HOST_USER,
            settings.EMAIL_HOST_PASSWORD,
            settings.DEFAULT_FROM_EMAIL,
        )) else 'unconfigured'
    return 'custom'


def email_delivery_configured():
    return email_delivery_mode() != 'unconfigured'


def email_delivery_status():
    mode = email_delivery_mode()
    messages = {
        'smtp': 'SMTP delivery is configured.',
        'custom': 'A custom email delivery backend is configured.',
        'preview': 'Local preview mode prints emails to the server console; it does not deliver to inboxes.',
        'test': 'Test delivery mode does not send email outside the application test environment.',
        'unconfigured': 'SMTP credentials and a verified sender must be configured before email can be delivered.',
    }
    return {
        'mode': mode,
        'configured': mode != 'unconfigured',
        'real_delivery': mode in {'smtp', 'custom'},
        'message': messages[mode],
    }


def _frontend_action_path(notification):
    link = notification.link or ''
    if link.startswith('/') and not link.startswith('/api/'):
        return link
    request_match = re.search(r'/purchase-requests/(\d+)', link)
    order_match = re.search(r'/purchase-orders/(\d+)', link)
    if request_match:
        return f'/procurement/requests/{request_match.group(1)}'
    if order_match:
        return f'/procurement/purchase-orders/{order_match.group(1)}'
    kind = notification.notification_type
    if kind.startswith('invoice_'):
        return '/finance/payables'
    if kind.startswith('payment_'):
        return '/finance/payments'
    if kind.startswith('budget_') or kind == Notification.TYPE_PO_EXCEEDING_BUDGET:
        return '/finance/budgets'
    if kind == Notification.TYPE_STAFF_ADVANCE_OVERDUE:
        return '/finance/expenses'
    if kind == Notification.TYPE_VALUATION_ADJUSTMENT:
        return '/inventory/movements'
    if kind == Notification.TYPE_JOURNAL_POSTING_FAILURE:
        return '/finance/reports'
    return '/notifications'


def _absolute_link(link):
    return urljoin(f'{settings.FRONTEND_BASE_URL}/', (link or '/notifications').lstrip('/'))


def queue_notification_email(notification_or_id, *, force=False):
    notification_id = getattr(notification_or_id, 'pk', notification_or_id)
    notification = Notification.objects.select_related('recipient', 'company').get(pk=notification_id)
    recipient = notification.recipient
    if not recipient.email:
        return None

    preference, _ = EmailNotificationPreference.objects.get_or_create(
        user=recipient, defaults={'company': notification.company},
    )
    category = notification_category(notification)
    if not force and (
        not preference.enabled
        or not getattr(preference, category)
        or (preference.required_only and not notification_requires_action(notification))
    ):
        return None

    context = {
        'notification': notification,
        'recipient': recipient,
        'company': notification.company,
        'action_url': _absolute_link(_frontend_action_path(notification)),
        'requires_action': notification_requires_action(notification),
    }
    return EmailDelivery.objects.get_or_create(
        notification=notification,
        defaults={
            'company': notification.company,
            'recipient': recipient,
            'recipient_email': recipient.email,
            'subject': f'{"Action required: " if context["requires_action"] else ""}{notification.title}',
            'text_body': render_to_string('notifications/email/notification.txt', context),
            'html_body': render_to_string('notifications/email/notification.html', context),
            'scheduled_at': timezone.now(),
        },
    )[0]


def queue_test_email(user):
    if not user.email:
        raise ValueError('Add an email address to your account before sending a test email.')
    context = {
        'recipient': user,
        'company': user.company,
        'action_url': _absolute_link('/notifications'),
    }
    return EmailDelivery.objects.create(
        company=user.company,
        recipient=user,
        recipient_email=user.email,
        subject='ConstructSaaS email notifications are ready',
        text_body=render_to_string('notifications/email/test.txt', context),
        html_body=render_to_string('notifications/email/test.html', context),
        scheduled_at=timezone.now(),
    )


def send_email_delivery(delivery):
    message = EmailMultiAlternatives(
        subject=delivery.subject,
        body=delivery.text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[delivery.recipient_email],
    )
    if delivery.html_body:
        message.attach_alternative(delivery.html_body, 'text/html')
    return message.send(fail_silently=False)


def attempt_email_delivery(delivery_or_id):
    """Claim and send one outbox record without allowing provider failures to escape."""
    delivery_id = getattr(delivery_or_id, 'pk', delivery_or_id)
    now = timezone.now()
    with transaction.atomic():
        delivery = EmailDelivery.objects.select_for_update().get(pk=delivery_id)
        if delivery.status in {EmailDelivery.STATUS_SENT, EmailDelivery.STATUS_CANCELLED}:
            return delivery
        if (
            delivery.status == EmailDelivery.STATUS_PROCESSING
            and delivery.last_attempt_at
            and delivery.last_attempt_at >= now - timedelta(minutes=15)
        ):
            return delivery
        delivery.status = EmailDelivery.STATUS_PROCESSING
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.save(update_fields=['status', 'attempts', 'last_attempt_at', 'updated_at'])

    try:
        sent_count = send_email_delivery(delivery)
        if sent_count != 1:
            raise RuntimeError('The email backend did not confirm delivery.')
    except Exception as error:
        delivery.last_error = str(error)[:2000]
        if delivery.attempts >= settings.EMAIL_NOTIFICATION_MAX_ATTEMPTS:
            delivery.status = EmailDelivery.STATUS_FAILED
        else:
            delivery.status = EmailDelivery.STATUS_PENDING
            delivery.scheduled_at = timezone.now() + timedelta(minutes=2 ** delivery.attempts)
        delivery.save(update_fields=['status', 'scheduled_at', 'last_error', 'updated_at'])
    else:
        delivery.status = EmailDelivery.STATUS_SENT
        delivery.sent_at = timezone.now()
        delivery.last_error = ''
        delivery.save(update_fields=['status', 'sent_at', 'last_error', 'updated_at'])
    return delivery
