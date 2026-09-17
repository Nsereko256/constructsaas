import re
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
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


def email_delivery_configured():
    backend = settings.EMAIL_BACKEND
    if backend.endswith(('console.EmailBackend', 'locmem.EmailBackend', 'dummy.EmailBackend')):
        return True
    return bool(settings.EMAIL_HOST and settings.DEFAULT_FROM_EMAIL)


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
