from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('procurement', '0016_purchase_request_partial_stock_issued')]

    operations = [
        migrations.AddField(
            model_name='supplierclaim',
            name='replacement_grn_item',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='replacement_for_supplier_claim', to='procurement.goodsreceivednoteitem'),
        ),
    ]
