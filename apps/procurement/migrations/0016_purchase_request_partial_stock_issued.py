from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0015_purchaseorderamendment_original_values')]

    operations = [
        migrations.AlterField(
            model_name='purchaserequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'), ('RETURNED', 'Returned for Correction'),
                    ('APPROVED', 'Approved'), ('REJECTED', 'Rejected'), ('PO_CREATED', 'PO Created'),
                    ('STOCK_ISSUE_REQUESTED', 'Stock Issue Requested'),
                    ('PARTIAL_STOCK_ISSUED', 'Partially Stock Issued'),
                    ('STOCK_ISSUED', 'Stock Issued'),
                ], default='PENDING', max_length=30,
            ),
        ),
    ]
