import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0013_purchaseorder_delivery_follow_up_owner_and_more'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(name='PurchaseOrderAmendment', fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('version', models.PositiveIntegerField()), ('reason', models.TextField()), ('proposed_values', models.JSONField()),
        ('status', models.CharField(choices=[('SUBMITTED','Submitted'),('APPROVED','Approved'),('REJECTED','Rejected')], default='SUBMITTED', max_length=12)),
        ('decision_reason', models.TextField(blank=True)), ('created_at', models.DateTimeField(auto_now_add=True)), ('decided_at', models.DateTimeField(blank=True, null=True)),
        ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='purchase_order_amendments', to='accounts.company')),
        ('purchase_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='amendments', to='procurement.purchaseorder')),
        ('submitted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='submitted_po_amendments', to=settings.AUTH_USER_MODEL)),
        ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='decided_po_amendments', to=settings.AUTH_USER_MODEL)),
    ], options={'ordering':['-version'], 'constraints':[models.UniqueConstraint(fields=('purchase_order','version'), name='unique_po_amendment_version')]})]
