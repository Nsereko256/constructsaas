from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import User


def accessible_projects(user, queryset):
    queryset = queryset.filter(company_id=user.company_id)
    today = timezone.localdate()
    active_assignment = Q(staff_assignments__user=user, staff_assignments__is_active=True) & (Q(staff_assignments__start_date__isnull=True) | Q(staff_assignments__start_date__lte=today)) & (Q(staff_assignments__end_date__isnull=True) | Q(staff_assignments__end_date__gte=today))
    if user.role == User.ROLE_PROJECT_MANAGER:
        return queryset.filter(Q(manager=user) | active_assignment).distinct()
    if user.role == User.ROLE_SITE_ENGINEER:
        return queryset.filter(Q(site_engineers=user) | active_assignment).distinct()
    return queryset


def can_access_project_chat(user, project):
    if not user.is_authenticated or user.company_id != project.company_id:
        return False
    if user.role == User.ROLE_ADMIN:
        return True
    if user.role == User.ROLE_PROJECT_MANAGER:
        return project.manager_id == user.id
    if user.role == User.ROLE_SITE_ENGINEER:
        return project.site_engineers.filter(pk=user.id).exists()
    return False


def accessible_chat_projects(user, queryset):
    queryset = queryset.filter(company_id=user.company_id)
    if user.role == User.ROLE_ADMIN:
        return queryset
    if user.role == User.ROLE_PROJECT_MANAGER:
        return queryset.filter(manager=user)
    if user.role == User.ROLE_SITE_ENGINEER:
        return queryset.filter(site_engineers=user)
    return queryset.none()


def accessible_project_sites(user, queryset):
    queryset = queryset.filter(project__company_id=user.company_id)
    if user.role in {User.ROLE_ADMIN, User.ROLE_PROCUREMENT_OFFICER, User.ROLE_STOREKEEPER, User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_FINANCE_VIEWER}:
        return queryset
    if user.role == User.ROLE_PROJECT_MANAGER:
        return queryset.filter(Q(manager=user) | Q(project__manager=user) | Q(site_engineers=user) | Q(project__site_engineers=user)).distinct()
    if user.role == User.ROLE_SITE_ENGINEER:
        return queryset.filter(Q(site_engineers=user) | Q(project__site_engineers=user)).distinct()
    return queryset.none()


def accessible_purchase_requests(user, queryset):
    queryset = queryset.filter(company_id=user.company_id)
    if user.role == User.ROLE_PROJECT_MANAGER:
        return queryset.filter(project__manager=user)
    if user.role == User.ROLE_SITE_ENGINEER:
        return queryset.filter(Q(project__site_engineers=user) | Q(requested_by=user)).distinct()
    return queryset


def accessible_purchase_orders(user, queryset):
    queryset = queryset.filter(company_id=user.company_id)
    if user.role == User.ROLE_STOREKEEPER:
        # The Storekeeper owns the physical GRN for both warehouse and
        # direct-to-site deliveries, so they must be able to see every company
        # PO that may arrive for receipt.
        return queryset
    if user.role == User.ROLE_PROJECT_MANAGER:
        return queryset.filter(project__manager=user)
    if user.role == User.ROLE_SITE_ENGINEER:
        return queryset.filter(
            Q(project__site_engineers=user) | Q(purchase_request__requested_by=user),
            delivery_destination='SITE',
        ).distinct()
    return queryset
