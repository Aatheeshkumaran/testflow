from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import User

R = User.Role
ADMIN_ONLY = (R.ADMIN,)
STAFF = (R.ADMIN, R.MANAGEMENT)          # organisation-wide roles
ALL_ROLES = (R.ADMIN, R.MANAGEMENT, R.MENTOR)


def role_required(*roles):
    """Backend authorisation. Superusers count as Admin. Never rely on hidden buttons alone."""
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.user.effective_role not in roles:
                raise PermissionDenied("You do not have permission to open this page.")
            return view(request, *args, **kwargs)
        return login_required(wrapped)
    return decorator


def home_url_name(user):
    return {R.ADMIN: "control_center", R.MANAGEMENT: "overview", R.MENTOR: "workspace"}[user.effective_role]
