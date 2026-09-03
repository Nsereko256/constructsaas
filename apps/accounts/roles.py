"""Central role groups used by backend permission policies.

Keep these groups in one place so a role change is reviewed once and applied
consistently across API permissions, services, and future UI metadata.
"""

from .models import User


ADMIN = {User.ROLE_ADMIN}
STOREKEEPER_OR_ADMIN = {User.ROLE_STOREKEEPER, User.ROLE_ADMIN}
PROJECT_MANAGER_OR_ADMIN = {User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN}
PROCUREMENT_OR_ADMIN = {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN}
PURCHASE_REQUEST_SUBMITTERS = {
    User.ROLE_SITE_ENGINEER,
    User.ROLE_PROCUREMENT_OFFICER,
    User.ROLE_ADMIN,
}
SUPPLIER_READERS = {
    User.ROLE_PROJECT_MANAGER,
    User.ROLE_PROCUREMENT_OFFICER,
    User.ROLE_FINANCE_OFFICER,
    User.ROLE_FINANCE_MANAGER,
    User.ROLE_FINANCE_VIEWER,
    User.ROLE_ADMIN,
}
REPORT_USERS = {
    User.ROLE_PROJECT_MANAGER,
    User.ROLE_PROCUREMENT_OFFICER,
    User.ROLE_ADMIN,
}
