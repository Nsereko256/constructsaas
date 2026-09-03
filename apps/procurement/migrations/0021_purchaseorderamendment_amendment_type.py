from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0020_purchaserequest_work_order_site')]

    operations = [
        migrations.AddField(
            model_name='purchaseorderamendment',
            name='amendment_type',
            field=models.CharField(choices=[('CONTROLLED', 'Controlled amendment'), ('PRE_APPROVAL_EDIT', 'Pre-approval edit')], default='CONTROLLED', max_length=24),
        ),
    ]
