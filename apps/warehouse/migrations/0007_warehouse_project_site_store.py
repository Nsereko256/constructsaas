import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('warehouse', '0006_alter_stockmovement_transaction_type'), ('projects', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='warehouse', name='project',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='site_store', to='projects.project'),
        ),
    ]
