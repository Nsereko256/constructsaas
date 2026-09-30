"""Admin-only, read-only company setup checks. Never settle legacy stock here."""
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.finance.models import FinanceSettings, WorkflowConfirmation
from apps.materials.models import Material
from apps.notifications.email_services import email_delivery_status
from apps.notifications.models import EmailDelivery
from apps.projects.models import Project, ProjectStaffAssignment
from apps.suppliers.models import Supplier
from apps.warehouse.models import SiteTransfer, StockMovement, Warehouse
from .permissions import IsAdminOnly


class CompanyReadinessAPIView(APIView):
    permission_classes = [IsAdminOnly]

    def get(self, request):
        company = request.user.company
        users = User.objects.filter(company=company, is_active=True)
        settings = FinanceSettings.objects.filter(company=company).first()
        finance = bool(settings and settings.soft_finance_enabled)
        required_roles = [User.ROLE_PROCUREMENT_OFFICER, User.ROLE_STOREKEEPER]
        projects = Project.objects.filter(company=company, is_active=True).exclude(status=Project.STATUS_COMPLETED)
        if projects.exists():
            required_roles += [User.ROLE_PROJECT_MANAGER, User.ROLE_SITE_ENGINEER]
        if finance:
            required_roles += [User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER]
        roles = set(users.values_list('role', flat=True))
        missing = [dict(User.ROLE_CHOICES)[role] for role in required_roles if role not in roles]
        today = timezone.localdate()
        assignments = ProjectStaffAssignment.objects.filter(
            project__company=company, is_active=True, user__is_active=True,
        ).filter(Q(start_date__isnull=True) | Q(start_date__lte=today)).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today),
        )
        managers = assignments.filter(role='MANAGER', user__role=User.ROLE_PROJECT_MANAGER).values('project_id')
        engineers = assignments.filter(role='ENGINEER', user__role=User.ROLE_SITE_ENGINEER).values('project_id')
        missing_manager = projects.exclude(Q(manager__is_active=True, manager__role=User.ROLE_PROJECT_MANAGER) | Q(pk__in=managers)).count()
        missing_engineer = projects.exclude(Q(site_engineers__is_active=True, site_engineers__role=User.ROLE_SITE_ENGINEER) | Q(pk__in=engineers)).count()
        pending_opening = WorkflowConfirmation.objects.filter(
            company=company, document_type=WorkflowConfirmation.DOCUMENT_OPENING_STOCK,
            status=WorkflowConfirmation.STATUS_PENDING,
        ).count()
        dispatched = SiteTransfer.objects.filter(company=company, status=SiteTransfer.STATUS_DISPATCHED).count()
        site_balances = StockMovement.objects.filter(company=company, warehouse__project__isnull=False).values(
            'warehouse_id', 'material_id',
        ).annotate(balance=Sum('quantity_effect')).exclude(balance=0).count()
        email = email_delivery_status()
        failed = EmailDelivery.objects.filter(company=company, status=EmailDelivery.STATUS_FAILED).count()
        pending_email = EmailDelivery.objects.filter(company=company, status__in=[EmailDelivery.STATUS_PENDING, EmailDelivery.STATUS_PROCESSING]).count()
        missing_email = users.filter(Q(email='') | Q(email__isnull=True)).count()
        checks = []

        def add(key, label, ready, detail, href, owner='Admin'):
            checks.append({'key': key, 'label': label, 'status': 'ready' if ready else 'attention',
                           'detail': detail, 'href': href, 'owner': owner})

        warehouse = Warehouse.objects.filter(company=company, is_active=True, is_default=True, project__isnull=True).exists()
        add('warehouse', 'Receiving warehouse', warehouse,
            'An active default warehouse is configured.' if warehouse else 'Set an active default warehouse before importing or receiving stock.', '/inventory/bin-locations')
        materials = Material.objects.filter(company=company, is_active=True).count()
        add('materials', 'Material catalogue', materials > 0, f'{materials} active materials. Use Excel import to onboard existing stock.', '/inventory')
        suppliers = Supplier.objects.filter(company=company, is_active=True).count()
        add('suppliers', 'Supplier catalogue', suppliers > 0, f'{suppliers} active suppliers available for purchase orders.', '/suppliers', 'Procurement')
        add('roles', 'Responsible teams', not missing, 'Missing active roles: ' + ', '.join(missing) if missing else 'All required operational roles have active users.', '/team')
        add('assignments', 'Project responsibility', not missing_manager and not missing_engineer,
            f'{missing_manager} projects without an active manager; {missing_engineer} without an active engineer.', '/projects')
        add('opening_stock', 'Opening-stock approval', not pending_opening,
            f'{pending_opening} imports await Admin approval and posting.' if pending_opening else 'No submitted opening-stock imports await Admin posting. Import is optional for companies starting with no stock.', '/inventory')
        add('legacy_stock', 'Legacy stock obligations', not dispatched and not site_balances,
            f'{dispatched} unacknowledged legacy transfers; {site_balances} non-zero site-store material balances. Preserve history and arrange a controlled reconciliation; retired Site custody transactions remain disabled.', '/inventory/movements')
        add('email', 'Action email delivery', email['real_delivery'] and not failed and not missing_email,
            f"{email['message']} {pending_email} queued; {failed} failed; {missing_email} active users without email. In-app workflows remain available.", '/settings')
        return Response({'checked_at': timezone.now(), 'finance_enabled': finance,
                         'attention_count': sum(check['status'] == 'attention' for check in checks), 'checks': checks})
