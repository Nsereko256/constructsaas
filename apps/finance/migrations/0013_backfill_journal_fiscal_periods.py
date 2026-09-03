from calendar import monthrange

from django.db import migrations


def backfill_periods(apps, schema_editor):
    FiscalPeriod = apps.get_model('finance', 'FiscalPeriod')
    JournalEntry = apps.get_model('finance', 'JournalEntry')
    journals = JournalEntry.objects.filter(fiscal_period__isnull=True).order_by('company_id', 'date')
    for journal in journals.iterator():
        period = FiscalPeriod.objects.filter(
            company_id=journal.company_id,
            start_date__lte=journal.date,
            end_date__gte=journal.date,
        ).first()
        if not period:
            period, _ = FiscalPeriod.objects.get_or_create(
                company_id=journal.company_id,
                name=f'{journal.date:%Y-%m}',
                defaults={
                    'start_date': journal.date.replace(day=1),
                    'end_date': journal.date.replace(
                        day=monthrange(journal.date.year, journal.date.month)[1],
                    ),
                },
            )
        JournalEntry.objects.filter(pk=journal.pk).update(fiscal_period=period)


class Migration(migrations.Migration):
    dependencies = [('finance', '0012_seed_default_ledger_configuration')]

    operations = [migrations.RunPython(backfill_periods, migrations.RunPython.noop)]
