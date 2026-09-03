from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0004_unique_po_per_purchase_request'),
    ]

    operations = [
        migrations.AlterField(
            model_name='purchaserequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('APPROVED', 'Approved'),
                    ('REJECTED', 'Rejected'),
                    ('PO_CREATED', 'PO Created'),
                    ('STOCK_ISSUED', 'Stock Issued'),
                ],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
