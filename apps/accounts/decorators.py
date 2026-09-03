from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User


def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


site_engineer_required = role_required(User.ROLE_SITE_ENGINEER, User.ROLE_ADMIN)
storekeeper_required = role_required(User.ROLE_STOREKEEPER, User.ROLE_ADMIN)
project_manager_required = role_required(User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN)
procurement_required = role_required(User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN)
admin_required = role_required(User.ROLE_ADMIN)
