from decimal import Decimal, ROUND_HALF_UP

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


MONEY = Decimal('0.01')
RATE = Decimal('0.000001')


def migrate_historical_valuation(apps, schema_editor):
    StockMovement = apps.get_model('warehouse', 'StockMovement')
    Warehouse = apps.get_model('warehouse', 'Warehouse')

    company_ids = StockMovement.objects.order_by().values_list('company_id', flat=True).distinct()
    warehouse_by_company = {}
    for company_id in company_ids:
        warehouse, _ = Warehouse.objects.get_or_create(
            company_id=company_id,
            code='MAIN',
            defaults={'name': 'Main Warehouse', 'is_default': True, 'is_active': True},
        )
        warehouse_by_company[company_id] = warehouse.pk

    state = {}
    movements = StockMovement.objects.order_by('company_id', 'material_id', 'date', 'created_at', 'pk')
    for movement in movements.iterator():
        warehouse_id = warehouse_by_company[movement.company_id]
        key = (movement.company_id, movement.material_id, warehouse_id)
        quantity, value = state.get(key, (Decimal('0.00'), Decimal('0.00')))
        movement_quantity = Decimal(movement.quantity)
        recorded_rate = Decimal(movement.unit_price or 0).quantize(RATE, rounding=ROUND_HALF_UP)
        movement_value = (movement_quantity * recorded_rate).quantize(MONEY, rounding=ROUND_HALF_UP)
        incoming = movement.movement_type in {'IN', 'ADJUST_IN'}
        if incoming:
            new_quantity = quantity + movement_quantity
            new_value = value + movement_value
            valuation_rate = (
                Decimal('0.000000') if new_quantity == 0
                else (new_value / new_quantity).quantize(RATE, rounding=ROUND_HALF_UP)
            )
            quantity_effect = movement_quantity
            value_effect = movement_value
            transaction_type = 'QUANTITY_ADJUSTMENT' if movement.movement_type == 'ADJUST_IN' else 'RECEIPT'
        else:
            # The legacy issue price is the only reliable historical issue rate.
            valuation_rate = recorded_rate
            new_quantity = quantity - movement_quantity
            new_value = value - movement_value
            quantity_effect = -movement_quantity
            value_effect = -movement_value
            transaction_type = (
                'QUANTITY_ADJUSTMENT' if movement.movement_type == 'ADJUST_OUT'
                else 'PROJECT_ISSUE' if movement.project_id else 'LEGACY'
            )
        StockMovement.objects.filter(pk=movement.pk).update(
            warehouse_id=warehouse_id,
            transaction_type=transaction_type,
            unit_cost=recorded_rate,
            valuation_rate=valuation_rate,
            total_cost=movement_value,
            quantity_effect=quantity_effect,
            value_effect=value_effect,
        )
        state[key] = (new_quantity, new_value)


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('procurement', '0009_alter_documentsequence_document_type_and_more'),
        ('warehouse', '0004_alter_stockmovement_purchase_order_item'),
    ]

    operations = [
        migrations.CreateModel(
            name='Warehouse',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150)),
                ('code', models.CharField(max_length=30)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('is_default', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='warehouses', to='accounts.company')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.AddField(
            model_name='stockmovement', name='authorization_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='stockmovement', name='authorized_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='authorized_stock_valuations', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='stockmovement', name='goods_received_note_item',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movement', to='procurement.goodsreceivednoteitem'),
        ),
        migrations.AddField(
            model_name='stockmovement', name='original_movement',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='return_movements', to='warehouse.stockmovement'),
        ),
        migrations.AddField(
            model_name='stockmovement', name='quantity_effect',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='stockmovement', name='total_cost',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='stockmovement', name='transaction_type',
            field=models.CharField(choices=[('LEGACY', 'Legacy movement'), ('OPENING', 'Opening balance'), ('RECEIPT', 'Valued receipt'), ('PROJECT_ISSUE', 'Project issue'), ('PROJECT_RETURN', 'Project return'), ('SUPPLIER_RETURN', 'Supplier return'), ('DAMAGE', 'Damage'), ('WRITE_OFF', 'Write off'), ('QUANTITY_ADJUSTMENT', 'Quantity adjustment'), ('VALUATION_ADJUSTMENT', 'Valuation adjustment')], default='LEGACY', max_length=30),
        ),
        migrations.AddField(
            model_name='stockmovement', name='unit_cost',
            field=models.DecimalField(decimal_places=6, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='stockmovement', name='valuation_rate',
            field=models.DecimalField(decimal_places=6, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='stockmovement', name='value_effect',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='stockmovement', name='warehouse',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='warehouse.warehouse'),
        ),
        migrations.AddConstraint(
            model_name='warehouse',
            constraint=models.UniqueConstraint(fields=('company', 'code'), name='unique_company_warehouse_code'),
        ),
        migrations.AddConstraint(
            model_name='warehouse',
            constraint=models.UniqueConstraint(condition=models.Q(('is_default', True)), fields=('company',), name='one_default_warehouse_per_company'),
        ),
        migrations.RunPython(migrate_historical_valuation, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='stockmovement', name='warehouse',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_movements', to='warehouse.warehouse'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gte', 0)), name='stock_movement_quantity_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(condition=models.Q(('unit_cost__gte', 0)), name='stock_movement_unit_cost_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(condition=models.Q(('valuation_rate__gte', 0)), name='stock_valuation_rate_nonnegative'),
        ),
        migrations.AddConstraint(
            model_name='stockmovement',
            constraint=models.CheckConstraint(condition=models.Q(('total_cost__gte', 0)), name='stock_total_cost_nonnegative'),
        ),
    ]
