from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('procurement', '0023_purchaserequest_manager_approved_by'),
    ]

    operations = [
        migrations.AddField(
            model_name='purchaserequest',
            name='delivery_destination',
            field=models.CharField(choices=[('WAREHOUSE', 'Main Warehouse'), ('SITE', 'Direct to Site')], default='WAREHOUSE', max_length=20),
        ),
        migrations.AddField(
            model_name='purchaserequest',
            name='required_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
