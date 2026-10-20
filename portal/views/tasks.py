from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.permissions import ALL_ROLES, STAFF, role_required

from .. import analytics, services
from ..forms import TaskForm, TaskUpdateForm
from ..models import MentorTask
from .helpers import get_scoped_or_404, paginate


@role_required(*ALL_ROLES)
def tasks_list(request):
    qs = analytics.tasks_for(request.user).select_related("assigned_to", "created_by")
    status, mentor = request.GET.get("status", ""), request.GET.get("mentor", "")
    if status == "OVERDUE":
        qs = qs.filter(deadline__lt=timezone.now()).exclude(status=MentorTask.Status.COMPLETED)
    elif status == "OPEN":
        qs = qs.exclude(status=MentorTask.Status.COMPLETED)
    elif status in MentorTask.Status.values:
        qs = qs.filter(status=status)
    if mentor.isdigit() and request.user.is_staff_role:
        qs = qs.filter(assigned_to_id=int(mentor))
    ctx = {"page": paginate(request, qs), "status": status, "mentor": mentor, "statuses": MentorTask.Status.choices,
           "mentors": analytics.active_mentors() if request.user.is_staff_role else None}
    return render(request, "portal/tasks_list.html", ctx)


@role_required(*STAFF)
def tasks_new(request):
    form = TaskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        task = form.save(commit=False)
        task.created_by = request.user
        task.save()
        services.task_assigned(task)
        messages.success(request, f"Task assigned to {task.assigned_to.display_name}.")
        return redirect("tasks_detail", pk=task.pk)
    return render(request, "portal/form.html", {"form": form, "title": "Assign a task to a mentor", "back": "tasks_list"})


@role_required(*STAFF)
def tasks_edit(request, pk):
    task = get_scoped_or_404(MentorTask.objects.all(), pk)
    form = TaskForm(request.POST or None, instance=task)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Task updated.")
        return redirect("tasks_detail", pk=task.pk)
    return render(request, "portal/form.html", {"form": form, "title": f"Edit {task.title}", "back": "tasks_list"})


@role_required(*ALL_ROLES)
def tasks_detail(request, pk):
    task = get_scoped_or_404(analytics.tasks_for(request.user).select_related("assigned_to", "created_by"), pk)
    can_update = request.user.is_mentor_role and task.assigned_to_id == request.user.id
    form = TaskUpdateForm(request.POST or None, initial={"status": task.status, "progress": task.progress})
    if request.method == "POST":
        if not can_update:
            raise PermissionDenied("Only the assigned mentor can post progress updates.")
        if form.is_valid():
            d = form.cleaned_data
            services.apply_task_update(task, request.user, d["status"], d["progress"], d["note"].strip())
            messages.success(request, "Progress saved.")
            return redirect("tasks_detail", pk=task.pk)
    return render(request, "portal/tasks_detail.html", {"task": task, "updates": task.updates.select_related("updated_by"),
                                                        "form": form, "can_update": can_update})
