from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0003_purchase_order_workflow'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='purchaseorder',
            constraint=models.UniqueConstraint(
                condition=Q(purchase_request__isnull=False),
                fields=('purchase_request',),
                name='unique_purchase_order_per_purchase_request',
            ),
        ),
    ]
