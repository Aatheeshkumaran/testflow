from django.conf import settings


def identity(request):
    """Sidebar identity comes from the authenticated user on every request. Nothing is hardcoded."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    from portal.models import Notification
    match = getattr(request, "resolver_match", None)
    section = (match.url_name or "").split("_")[0] if match else ""
    section = {"users": "control", "tests": "tests"}.get(section, section)
    return {
        "unread_count": Notification.objects.filter(recipient=user, is_read=False).count(),
        "nav_section": section,
        "attention_threshold": settings.TF_ATTENTION_THRESHOLD,
    }
