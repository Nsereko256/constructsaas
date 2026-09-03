from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('procurement', '0005_purchase_request_stock_issued_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='delivery_destination',
            field=models.CharField(
                choices=[('WAREHOUSE', 'Warehouse'), ('SITE', 'Direct to site')],
                default='WAREHOUSE',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='received_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='received_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='received_purchase_orders',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='purchaserequest',
            name='status',
            field=models.CharField(
                choices=[
                    ('PENDING', 'Pending'),
                    ('APPROVED', 'Approved'),
                    ('REJECTED', 'Rejected'),
                    ('PO_CREATED', 'PO Created'),
                    ('STOCK_ISSUE_REQUESTED', 'Stock Issue Requested'),
                    ('STOCK_ISSUED', 'Stock Issued'),
                ],
                default='PENDING',
                max_length=30,
            ),
        ),
    ]
