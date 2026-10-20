from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.permissions import ALL_ROLES, role_required

from ..models import Notification
from .helpers import paginate


@role_required(*ALL_ROLES)
def notifications(request):
    qs = Notification.objects.filter(recipient=request.user)       # recipient-level access control
    if request.GET.get("show") == "unread":
        qs = qs.filter(is_read=False)
    elif request.GET.get("show") == "open":
        qs = qs.filter(resolved_at__isnull=True)
    return render(request, "portal/notifications.html", {"page": paginate(request, qs), "show": request.GET.get("show", "")})


@require_POST
@role_required(*ALL_ROLES)
def notifications_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    n.is_read = True
    n.save(update_fields=["is_read"])
    return redirect("notifications")


@require_POST
@role_required(*ALL_ROLES)
def notifications_read_all(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("notifications")


@role_required(*ALL_ROLES)
def notifications_open(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not n.is_read:
        n.is_read = True
        n.save(update_fields=["is_read"])
    target = n.url if n.url and url_has_allowed_host_and_scheme(n.url, allowed_hosts=None) else "notifications"
    return redirect(target)
