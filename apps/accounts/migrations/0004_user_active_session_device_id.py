from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_user_active_session_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='active_session_device_id',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
