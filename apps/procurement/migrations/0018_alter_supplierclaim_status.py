from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0017_supplierclaim_replacement_grn_item')]

    operations = [
        migrations.AlterField(
            model_name='supplierclaim',
            name='status',
            field=models.CharField(choices=[
                ('OPEN', 'Open'), ('AWAITING_SUPPLIER', 'Awaiting supplier'),
                ('RETURN_PENDING', 'Return pending'), ('REPLACEMENT_PENDING', 'Replacement pending'),
                ('REPLACEMENT_RECEIVED', 'Replacement received - confirm closure'),
                ('CREDIT_PENDING', 'Credit note pending'), ('RESOLVED', 'Resolved'), ('CANCELLED', 'Cancelled'),
            ], default='OPEN', max_length=30),
        ),
    ]
