from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('low_stock', 'Low stock'), ('pr_submitted', 'PR submitted'), ('pr_approved', 'PR approved'), ('pr_rejected', 'PR rejected'), ('po_created', 'PO created'), ('po_received', 'PO received'), ('system', 'System')], max_length=30)),
                ('level', models.CharField(choices=[('info', 'Info'), ('success', 'Success'), ('warning', 'Warning'), ('danger', 'Danger')], default='info', max_length=10)),
                ('title', models.CharField(max_length=180)),
                ('message', models.TextField()),
                ('link', models.CharField(blank=True, max_length=500)),
                ('is_read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='accounts.company')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['company', 'recipient', 'is_read', '-created_at'], name='notificatio_company_f079c9_idx'),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['company', 'notification_type', '-created_at'], name='notificatio_company_719c72_idx'),
        ),
    ]
