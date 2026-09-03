from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import json

from django.conf import settings
from django.db import models, transaction

from apps.accounts.models import User
from apps.materials.models import Material
from .models import Notification, WebPushSubscription


def send_web_push_notification(notification):
    """Deliver an existing in-app notification to the user's opted-in devices."""
    if not settings.WEB_PUSH_VAPID_PUBLIC_KEY or not settings.WEB_PUSH_VAPID_PRIVATE_KEY:
        return 0

    from pywebpush import WebPushException, webpush

    payload = json.dumps({
        'title': notification.title,
        'body': notification.message,
        'link': notification.link or '/notifications',
        'tag': f'construct-notification-{notification.pk}',
    })
    delivered = 0
    subscriptions = WebPushSubscription.objects.filter(
        company=notification.company, user=notification.recipient,
    )
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.WEB_PUSH_VAPID_PRIVATE_KEY,
                vapid_claims=settings.WEB_PUSH_VAPID_CLAIMS,
            )
            delivered += 1
        except WebPushException as error:
            status_code = getattr(getattr(error, 'response', None), 'status_code', None)
            if status_code in {404, 410}:
                subscription.delete()
        except Exception:
            # Push is an optional delivery channel. It must never interrupt an
            # already-completed procurement or finance workflow transaction.
            continue
    return delivered


def get_unread_count(user, company=None):
    if user is None or not user.is_authenticated:
        return 0
    company = company or getattr(user, 'company', None)
    if company is None:
        return 0
    return Notification.objects.for_company(company).for_recipient(user).unread().count()


def push_unread_count(user, company=None):
    company = company or getattr(user, 'company', None)
    if user is None or not user.is_authenticated or company is None:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        f'notify_user_{user.id}',
        {
            'type': 'notification.count',
            'unread_count': get_unread_count(user, company),
        },
    )


def send_notification(user, notification_type, level, title, message, link=None):
    company = getattr(user, 'company', None)
    if user is None or not user.is_authenticated or company is None:
        raise ValueError('A logged-in user with a company is required to send a notification.')

    notification = Notification.objects.create(
        company=company,
        recipient=user,
        notification_type=notification_type,
        level=level,
        title=title,
        message=message,
        link=link or '',
    )

    channel_layer = get_channel_layer()
    if channel_layer is not None:
        try:
            async_to_sync(channel_layer.group_send)(
                f'notify_user_{user.id}',
                {
                    'type': 'notification.message',
                    'notification': serialize_notification(notification),
                    'unread_count': get_unread_count(user, company),
                },
            )
        except Exception:
            # Persisted in-app notifications must not roll back or turn a
            # completed approval into a 500 when realtime delivery is down.
            pass

    transaction.on_commit(lambda: send_web_push_notification(notification))

    return notification


def check_low_stock_for_company(company):
    if company is None:
        return []

    recipients = User.objects.filter(
        company=company,
        role__in=[
            User.ROLE_STOREKEEPER,
            User.ROLE_PROJECT_MANAGER,
            User.ROLE_ADMIN,
        ],
        is_active=True,
    )
    if not recipients.exists():
        return []

    created_notifications = []
    low_stock_materials = (
        Material.objects.for_company(company)
        .with_current_stock()
        .filter(is_active=True, current_stock_value__lte=models.F('min_stock_level'))
        .select_related('category')
        .order_by('name')
    )

    for material in low_stock_materials:
        link = f'/api/materials/{material.pk}/'
        title = f'Low stock: {material.code}'
        message = (
            f'{material.name} is at {material.current_stock_value} '
            f'{material.get_unit_display()} against minimum level {material.min_stock_level}.'
        )
        for recipient in recipients:
            duplicate_exists = Notification.objects.for_company(company).filter(
                recipient=recipient,
                notification_type=Notification.TYPE_LOW_STOCK,
                link=link,
                is_read=False,
            ).exists()
            if duplicate_exists:
                continue
            created_notifications.append(
                send_notification(
                    recipient,
                    Notification.TYPE_LOW_STOCK,
                    Notification.LEVEL_WARNING,
                    title,
                    message,
                    link,
                )
            )

    return created_notifications


def serialize_notification(notification):
    return {
        'id': notification.id,
        'notification_type': notification.notification_type,
        'notification_type_label': notification.get_notification_type_display(),
        'level': notification.level,
        'level_label': notification.get_level_display(),
        'title': notification.title,
        'message': notification.message,
        'link': notification.link,
        'is_read': notification.is_read,
        'created_at': notification.created_at.isoformat(),
    }
