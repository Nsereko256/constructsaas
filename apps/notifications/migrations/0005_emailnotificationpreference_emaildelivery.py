import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('notifications', '0004_alter_notification_notification_type')]

    operations = [
        migrations.CreateModel(
            name='EmailNotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enabled', models.BooleanField(default=True)),
                ('required_only', models.BooleanField(default=True)),
                ('procurement', models.BooleanField(default=True)),
                ('inventory', models.BooleanField(default=True)),
                ('projects', models.BooleanField(default=True)),
                ('finance', models.BooleanField(default=True)),
                ('system', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_notification_preferences', to='accounts.company')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='email_notification_preference', to='accounts.user')),
            ],
        ),
        migrations.CreateModel(
            name='EmailDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_email', models.EmailField(max_length=254)),
                ('subject', models.CharField(max_length=255)),
                ('text_body', models.TextField()),
                ('html_body', models.TextField()),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('sent', 'Sent'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], default='pending', max_length=16)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('scheduled_at', models.DateTimeField()),
                ('last_attempt_at', models.DateTimeField(blank=True, null=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('provider_message_id', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_deliveries', to='accounts.company')),
                ('notification', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='email_delivery', to='notifications.notification')),
                ('recipient', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='email_deliveries', to='accounts.user')),
            ],
            options={'ordering': ['scheduled_at', 'id']},
        ),
        migrations.AddIndex(model_name='emailnotificationpreference', index=models.Index(fields=['company', 'enabled'], name='emailpref_company_enabled_idx')),
        migrations.AddIndex(model_name='emaildelivery', index=models.Index(fields=['status', 'scheduled_at'], name='emaildelivery_status_due_idx')),
        migrations.AddIndex(model_name='emaildelivery', index=models.Index(fields=['company', '-created_at'], name='email_company_created_idx')),
    ]
