from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ForcedPasswordChangeForm, UserCreateForm, UserEditForm
from .models import AuditLog, User, audit
from .permissions import ADMIN_ONLY, home_url_name, role_required


class RoleAwareLoginView(LoginView):
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse(home_url_name(self.request.user))

    def get_success_url(self):
        return self.get_redirect_url() or self.get_default_redirect_url()


@login_required
def home(request):
    return redirect(home_url_name(request.user))


def permission_denied(request, exception=None):
    return render(request, "403.html", {"message": str(exception) if exception else ""}, status=403)


@login_required
def change_password(request):
    forced = request.user.must_change_password
    form = ForcedPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])
        update_session_auth_hash(request, user)
        messages.success(request, "Password updated.")
        return redirect(home_url_name(user))
    return render(request, "accounts/change_password.html", {"form": form, "forced": forced})


# ---------------------------------------------------------------- Admin Control Center
@role_required(*ADMIN_ONLY)
def control_center(request):
    from portal.analytics import org_counts
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    users = User.objects.all().order_by("-is_active", "role", "username")
    if q:
        users = users.filter(Q(username__icontains=q) | Q(first_name__icontains=q) |
                             Q(last_name__icontains=q) | Q(email__icontains=q))
    if role in User.Role.values:
        users = users.filter(role=role)
    ctx = {
        "users": users, "q": q, "role_filter": role, "roles": User.Role.choices,
        "counts": org_counts(), "audit": AuditLog.objects.select_related("actor")[:12],
    }
    return render(request, "accounts/control_center.html", ctx)


@role_required(*ADMIN_ONLY)
def user_create(request):
    form = UserCreateForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request.user, "Created account", user.username, f"role={user.role}")
        messages.success(request, f"Account '{user.username}' created. They must set a new password at first login.")
        return redirect("control_center")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Create account", "editing": None})


@role_required(*ADMIN_ONLY)
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    old_role, old_active = target.role, target.is_active
    form = UserEditForm(request.POST or None, request.FILES or None, instance=target, actor=request.user)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        notes = []
        if user.role != old_role:
            notes.append(f"role {old_role}→{user.role}")
        if user.is_active != old_active:
            notes.append(f"active {old_active}→{user.is_active}")
        if form.cleaned_data.get("new_temp_password"):
            notes.append("password reset")
        audit(request.user, "Edited account", user.username, "; ".join(notes))
        messages.success(request, "Account updated.")
        return redirect("control_center")
    return render(request, "accounts/user_form.html", {"form": form, "title": f"Edit {target.username}", "editing": target})


@require_POST
@role_required(*ADMIN_ONLY)
def user_toggle(request, pk):
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("control_center")
    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    audit(request.user, "Activated account" if target.is_active else "Deactivated account", target.username)
    messages.success(request, f"{target.username} is now {'active' if target.is_active else 'inactive'}.")
    return redirect("control_center")
