from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('projects', '0002_chatroom_chatmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='site_engineer',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_projects',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
