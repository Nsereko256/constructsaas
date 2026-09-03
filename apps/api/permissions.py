from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User
from apps.accounts.roles import (
    ADMIN,
    PROCUREMENT_OR_ADMIN,
    PROJECT_MANAGER_OR_ADMIN,
    PURCHASE_REQUEST_SUBMITTERS,
    REPORT_USERS,
    STOREKEEPER_OR_ADMIN,
    SUPPLIER_READERS,
)


class HasCompanyAndRole(BasePermission):
    allowed_roles = set()

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'company_id', None)
            and user.company.is_active
            and user.role in self.allowed_roles
        )

    def has_object_permission(self, request, view, obj):
        company_id = getattr(obj, 'company_id', None)
        if company_id is None and hasattr(obj, 'room'):
            company_id = getattr(obj.room, 'company_id', None)
        return self.has_permission(request, view) and company_id == request.user.company_id


class IsAdminOnly(HasCompanyAndRole):
    allowed_roles = ADMIN


class IsStorekeeperOrAdmin(HasCompanyAndRole):
    allowed_roles = STOREKEEPER_OR_ADMIN


class IsProjectManagerOrAdmin(HasCompanyAndRole):
    allowed_roles = PROJECT_MANAGER_OR_ADMIN


class IsProcurementOfficerOrAdmin(HasCompanyAndRole):
    allowed_roles = PROCUREMENT_OR_ADMIN


class IsSupplierReadUser(HasCompanyAndRole):
    """Roles that need supplier master data without supplier maintenance rights."""

    allowed_roles = SUPPLIER_READERS


class IsPurchaseOrderReceiver(HasCompanyAndRole):
    allowed_roles = {User.ROLE_STOREKEEPER, User.ROLE_ADMIN}


class IsPurchaseRequestSubmitterOrAdmin(HasCompanyAndRole):
    allowed_roles = PURCHASE_REQUEST_SUBMITTERS


class IsProcurementOfficerOrAdminAction(HasCompanyAndRole):
    allowed_roles = PROCUREMENT_OR_ADMIN


class IsReportsUser(HasCompanyAndRole):
    allowed_roles = REPORT_USERS


class IsAuthenticatedCompanyUser(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'company_id', None)
            and user.company.is_active
        )

    def has_object_permission(self, request, view, obj):
        company_id = getattr(obj, 'company_id', None)
        if company_id is None and hasattr(obj, 'room'):
            company_id = getattr(obj.room, 'company_id', None)
        # Operational child records such as WorkOrderSite inherit ownership
        # from their parent work order rather than storing company directly.
        if company_id is None and hasattr(obj, 'work_order'):
            company_id = getattr(obj.work_order, 'company_id', None)
        if company_id is None and hasattr(obj, 'project'):
            company_id = getattr(obj.project, 'company_id', None)
        return company_id == request.user.company_id


class IsCompanyUserReadOnlyOrStorekeeperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if (
            not user
            or not user.is_authenticated
            or not getattr(user, 'company_id', None)
            or not user.company.is_active
        ):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role in {User.ROLE_STOREKEEPER, User.ROLE_ADMIN}


class IsCompanyUserReadOnlyOrStorekeeperProcurementAdmin(IsCompanyUserReadOnlyOrStorekeeperAdmin):
    """Procurement owns the material catalogue; warehouse movements remain storekeeper-only."""

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            user = request.user
            return bool(
                request.method not in SAFE_METHODS
                and user
                and user.is_authenticated
                and getattr(user, 'company_id', None)
                and user.company.is_active
                and user.role == User.ROLE_PROCUREMENT_OFFICER
            )
        return True

    def has_object_permission(self, request, view, obj):
        company_id = getattr(obj, 'company_id', None)
        if company_id is None and hasattr(obj, 'project'):
            company_id = getattr(obj.project, 'company_id', None)
        if company_id != request.user.company_id:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in {
            User.ROLE_STOREKEEPER,
            User.ROLE_PROCUREMENT_OFFICER,
            User.ROLE_ADMIN,
        }


class IsCompanyUserReadOnlyOrProjectManagerAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if (
            not user
            or not user.is_authenticated
            or not getattr(user, 'company_id', None)
            or not user.company.is_active
        ):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role in {User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN}

    def has_object_permission(self, request, view, obj):
        company_id = getattr(obj, 'company_id', None)
        if company_id is None and hasattr(obj, 'project'):
            company_id = getattr(obj.project, 'company_id', None)
        if company_id != request.user.company_id:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role in {User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN}
