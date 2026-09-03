from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0010_offline_idempotency')]

    operations = [
        migrations.AddField(
            model_name='purchaserequest',
            name='technical_return_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='purchaserequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'), ('RETURNED', 'Returned for Correction'), ('APPROVED', 'Approved'),
                    ('REJECTED', 'Rejected'), ('PO_CREATED', 'PO Created'),
                    ('STOCK_ISSUE_REQUESTED', 'Stock Issue Requested'), ('STOCK_ISSUED', 'Stock Issued'),
                ],
                default='PENDING', max_length=30,
            ),
        ),
    ]
