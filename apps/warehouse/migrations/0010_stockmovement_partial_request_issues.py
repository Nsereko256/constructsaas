from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('warehouse', '0009_binlocation')]

    operations = [
        migrations.AlterField(
            model_name='stockmovement',
            name='purchase_request_item',
            field=models.ForeignKey(blank=True, null=True, on_delete=models.PROTECT, related_name='stock_movements', to='procurement.purchaserequestitem'),
        ),
    ]
