from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.accounts.models import Company

from .configuration_services import ensure_finance_settings


@receiver(post_save, sender=Company)
def create_company_finance_settings(sender, instance, created, **kwargs):
    if created:
        ensure_finance_settings(instance)
