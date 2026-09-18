from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('procurement', '0025_alter_documentsequence_document_type'),
        ('suppliers', '0003_supplier_contractor_specialty_supplier_is_contractor'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaserequest',
            name='preferred_supplier',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name='preferred_purchase_requests',
                to='suppliers.supplier',
            ),
        ),
    ]
