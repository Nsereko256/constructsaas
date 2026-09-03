from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [('procurement', '0009_alter_documentsequence_document_type_and_more')]

    operations = [
        migrations.AddField(
            model_name='purchaserequest', name='client_uuid',
            field=models.UUIDField(null=True, blank=True, default=None),
        ),
        migrations.AddField(
            model_name='goodsreceivednote', name='client_uuid',
            field=models.UUIDField(null=True, blank=True, default=None),
        ),
        migrations.AddConstraint(
            model_name='purchaserequest',
            constraint=models.UniqueConstraint(fields=('company', 'client_uuid'), condition=Q(client_uuid__isnull=False), name='unique_company_purchase_request_client_uuid'),
        ),
        migrations.AddConstraint(
            model_name='goodsreceivednote',
            constraint=models.UniqueConstraint(fields=('company', 'client_uuid'), condition=Q(client_uuid__isnull=False), name='unique_company_grn_client_uuid'),
        ),
    ]
