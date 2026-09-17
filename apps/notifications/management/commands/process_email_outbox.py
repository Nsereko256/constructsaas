from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.notifications.email_services import send_email_delivery
from apps.notifications.models import EmailDelivery


class Command(BaseCommand):
    help = 'Send due notification emails from the persistent outbox.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=settings.EMAIL_NOTIFICATION_BATCH_SIZE)

    def handle(self, *args, **options):
        now = timezone.now()
        EmailDelivery.objects.filter(
            status=EmailDelivery.STATUS_PROCESSING,
            last_attempt_at__lt=now - timedelta(minutes=15),
        ).update(status=EmailDelivery.STATUS_PENDING)

        sent = failed = 0
        for _ in range(max(options['limit'], 0)):
            with transaction.atomic():
                delivery = (
                    EmailDelivery.objects.select_for_update(skip_locked=True)
                    .filter(status=EmailDelivery.STATUS_PENDING, scheduled_at__lte=timezone.now())
                    .order_by('scheduled_at', 'id')
                    .first()
                )
                if delivery is None:
                    break
                delivery.status = EmailDelivery.STATUS_PROCESSING
                delivery.attempts += 1
                delivery.last_attempt_at = timezone.now()
                delivery.save(update_fields=['status', 'attempts', 'last_attempt_at', 'updated_at'])

            try:
                send_email_delivery(delivery)
            except Exception as error:
                failed += 1
                delivery.last_error = str(error)[:2000]
                if delivery.attempts >= settings.EMAIL_NOTIFICATION_MAX_ATTEMPTS:
                    delivery.status = EmailDelivery.STATUS_FAILED
                else:
                    delivery.status = EmailDelivery.STATUS_PENDING
                    delivery.scheduled_at = timezone.now() + timedelta(minutes=2 ** delivery.attempts)
                delivery.save(update_fields=['status', 'scheduled_at', 'last_error', 'updated_at'])
            else:
                sent += 1
                delivery.status = EmailDelivery.STATUS_SENT
                delivery.sent_at = timezone.now()
                delivery.last_error = ''
                delivery.save(update_fields=['status', 'sent_at', 'last_error', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f'Email outbox processed: {sent} sent, {failed} failed.'))
