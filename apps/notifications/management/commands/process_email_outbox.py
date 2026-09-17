from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.notifications.email_services import attempt_email_delivery
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
                delivery_id = delivery.pk

            delivery = attempt_email_delivery(delivery_id)
            if delivery.status == EmailDelivery.STATUS_SENT:
                sent += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(f'Email outbox processed: {sent} sent, {failed} failed.'))
