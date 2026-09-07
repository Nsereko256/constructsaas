from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User
from .configuration_services import ensure_finance_settings, soft_finance_enabled


FINANCE_READ_ROLES = {
    User.ROLE_PROJECT_MANAGER,
    User.ROLE_PROCUREMENT_OFFICER,
    User.ROLE_FINANCE_OFFICER,
    User.ROLE_FINANCE_MANAGER,
    User.ROLE_FINANCE_VIEWER,
    User.ROLE_ADMIN,
}

FINANCE_FOUNDATION_ROLES = {
    User.ROLE_FINANCE_OFFICER,
    User.ROLE_FINANCE_MANAGER,
    User.ROLE_FINANCE_VIEWER,
    User.ROLE_ADMIN,
}


class FinanceCompanyPermission(BasePermission):
    write_roles = {User.ROLE_ADMIN}

    def has_permission(self, request, view):
        user = request.user
        if not (
            user
            and user.is_authenticated
            and user.company_id
            and user.company.is_active
        ):
            return False
        settings = ensure_finance_settings(user.company)
        if not settings.soft_finance_enabled:
            raise PermissionDenied('Soft Finance / Cost Control is disabled for this company.', code='feature_disabled')
        path = request.path.lower()
        if '/supplier-invoices/' in path and not settings.invoice_tracking_enabled:
            raise PermissionDenied('Invoice tracking is disabled for this company.', code='invoice_tracking_disabled')
        payment_paths = ('/payments/', '/payment-batches/', '/payment-attachments/', '/payment-approvals/')
        if any(segment in path for segment in payment_paths) and not settings.payment_tracking_enabled:
            raise PermissionDenied('Payment tracking is disabled for this company.', code='payment_tracking_disabled')
        if request.method in SAFE_METHODS:
            return user.role in FINANCE_READ_ROLES
        return user.role in self.write_roles

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view) and obj.company_id == request.user.company_id


class FinanceProcurementWritePermission(FinanceCompanyPermission):
    write_roles = {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}


class FinanceAdminPermission(FinanceCompanyPermission):
    write_roles = {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}


class FinanceReviewPermission(FinanceCompanyPermission):
    """Finance Officers may complete ordinary reviews; overrides stay manager-only in services."""
    write_roles = {User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}


class FinanceManagerOnlyPermission(FinanceCompanyPermission):
    write_roles = {User.ROLE_FINANCE_MANAGER}


class FinanceFoundationPermission(BasePermission):
    write_roles = {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}

    def has_permission(self, request, view):
        user = request.user
        if not (
            user
            and user.is_authenticated
            and user.company_id
            and user.company.is_active
            and user.role in FINANCE_FOUNDATION_ROLES
        ):
            return False
        if not soft_finance_enabled(user.company):
            raise PermissionDenied('Soft Finance / Cost Control is disabled for this company.', code='feature_disabled')
        return request.method in SAFE_METHODS or user.role in self.write_roles

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view) and obj.company_id == request.user.company_id


class FinanceSubmissionPermission(FinanceCompanyPermission):
    # Procurement owns the technical demand for projectless warehouse
    # replenishment. It may submit that demand to Finance, but cannot approve
    # the resulting financial review or purchase order.
    write_roles = {
        User.ROLE_PROJECT_MANAGER,
        User.ROLE_PROCUREMENT_OFFICER,
        User.ROLE_FINANCE_OFFICER,
        User.ROLE_ADMIN,
    }


class FinancePreparationPermission(FinanceCompanyPermission):
    # A Finance Manager may step in to prepare work when needed. Approval and
    # posting controls remain separate, and service-level maker-checker rules
    # prevent a manager from approving their own prepared records.
    write_roles = {User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}


class FinanceSettingsPermission(BasePermission):
    """Settings stay reachable for the company admin even while Finance is off."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.company_id and user.company.is_active):
            return False
        if request.method in SAFE_METHODS:
            return user.role in FINANCE_READ_ROLES
        return user.role in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view) and obj.company_id == request.user.company_id
