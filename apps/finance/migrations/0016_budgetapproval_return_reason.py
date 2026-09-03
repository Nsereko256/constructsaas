from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0015_alter_account_system_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='budgetapproval',
            name='return_reason',
            field=models.TextField(blank=True),
        ),
    ]
