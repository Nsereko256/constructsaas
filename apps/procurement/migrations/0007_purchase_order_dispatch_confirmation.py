from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('procurement', '0006_stock_issue_request_and_po_delivery'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaseorder',
            name='dispatch_confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='purchaseorder',
            name='dispatch_confirmed_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='dispatch_confirmed_purchase_orders',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='purchaseorder',
            name='status',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Draft'),
                    ('PENDING', 'Pending'),
                    ('ORDERED', 'Ordered'),
                    ('DISPATCH_CONFIRMED', 'Dispatch Confirmed'),
                    ('PARTIAL', 'Partial'),
                    ('RECEIVED', 'Received'),
                    ('CANCELLED', 'Cancelled'),
                ],
                default='DRAFT',
                max_length=20,
            ),
        ),
    ]
