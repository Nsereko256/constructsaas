from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0025_financesettings_allow_unbudgeted_requests_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkflowConfirmation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('document_type', models.CharField(choices=[('PURCHASE_REQUEST', 'Purchase request'), ('STOCK_ISSUE', 'Stock issue'), ('PURCHASE_ORDER', 'Purchase order'), ('PO_DISPATCH', 'Purchase order dispatch'), ('WAREHOUSE_RECEIPT', 'Warehouse receipt'), ('SITE_RECEIPT', 'Direct-to-site receipt'), ('OPENING_STOCK', 'Opening stock import'), ('SUPPLIER_INVOICE', 'Supplier invoice'), ('PAYMENT', 'Payment')], max_length=30)),
                ('object_id', models.CharField(max_length=100)),
                ('object_label', models.CharField(max_length=200)),
                ('action_url', models.CharField(blank=True, max_length=300)),
                ('stage', models.CharField(choices=[('TECHNICAL', 'Technical confirmation'), ('STOCK', 'Stock confirmation'), ('FINANCE', 'Finance confirmation'), ('DISPATCH', 'Dispatch confirmation'), ('RECEIPT', 'Receipt confirmation'), ('POSTING', 'Posting confirmation')], max_length=20)),
                ('status', models.CharField(choices=[('PENDING', 'Awaiting confirmation'), ('CONFIRMED', 'Confirmed'), ('RETURNED', 'Returned for correction'), ('CANCELLED', 'Cancelled')], default='PENDING', max_length=20)),
                ('required_role', models.CharField(choices=[('site_engineer', 'Site Engineer'), ('storekeeper', 'Storekeeper'), ('project_manager', 'Project Manager'), ('procurement_officer', 'Procurement Officer'), ('finance_officer', 'Finance Officer'), ('finance_manager', 'Finance Manager'), ('finance_viewer', 'Finance Viewer'), ('admin', 'Admin')], max_length=32)),
                ('submitted_snapshot', models.JSONField(blank=True, default=dict)),
                ('confirmation_data', models.JSONField(blank=True, default=dict)),
                ('comments', models.TextField(blank=True)),
                ('return_reason', models.TextField(blank=True)),
                ('override_reason', models.TextField(blank=True)),
                ('version', models.PositiveIntegerField(default=1)),
                ('submitted_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='assigned_workflow_confirmations', to=settings.AUTH_USER_MODEL)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='workflow_confirmations', to='accounts.company')),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='confirmed_workflow_confirmations', to=settings.AUTH_USER_MODEL)),
                ('submitted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='submitted_workflow_confirmations', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-submitted_at', '-id']},
        ),
        migrations.AddConstraint(
            model_name='workflowconfirmation',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'PENDING')), fields=('company', 'document_type', 'object_id', 'stage'), name='unique_pending_workflow_confirmation'),
        ),
        migrations.AddIndex(
            model_name='workflowconfirmation',
            index=models.Index(fields=['company', 'status', 'required_role'], name='workflow_confirm_queue'),
        ),
        migrations.AddIndex(
            model_name='workflowconfirmation',
            index=models.Index(fields=['company', 'document_type', 'object_id'], name='workflow_confirm_record'),
        ),
    ]
