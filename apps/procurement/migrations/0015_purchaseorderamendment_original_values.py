from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('procurement', '0014_purchaseorderamendment')]

    operations = [
        migrations.AddField(
            model_name='purchaseorderamendment',
            name='original_values',
            field=models.JSONField(default=dict),
        ),
    ]
