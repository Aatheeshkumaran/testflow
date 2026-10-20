from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from accounts.permissions import ALL_ROLES, STAFF, role_required

from .. import analytics
from ..forms import BatchForm, DelayReasonForm
from ..models import BatchDelayReason
from .helpers import get_scoped_or_404


@role_required(*ALL_ROLES)
def batches_list(request):
    rows = []
    for b in analytics.batches_for(request.user).prefetch_related("mentors"):
        rows.append({"batch": b, "gap": analytics.batch_gap(b), "students": b.students.filter(is_active=True).count()})
    return render(request, "portal/batches_list.html", {"rows": rows})


@role_required(*STAFF)
def batches_new(request):
    form = BatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        b = form.save()
        messages.success(request, f"Batch '{b.name}' created.")
        return redirect("batches_detail", pk=b.pk)
    return render(request, "portal/form.html", {"form": form, "title": "New batch", "back": "batches_list"})


@role_required(*STAFF)
def batches_edit(request, pk):
    batch = get_scoped_or_404(analytics.batches_for(request.user), pk)
    form = BatchForm(request.POST or None, instance=batch)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Batch updated.")
        return redirect("batches_detail", pk=batch.pk)
    return render(request, "portal/form.html", {"form": form, "title": f"Edit {batch.name}", "back": "batches_list"})


@role_required(*ALL_ROLES)
def batches_detail(request, pk):
    batch = get_scoped_or_404(analytics.batches_for(request.user), pk)
    gap = analytics.batch_gap(batch)
    students = analytics.annotate_students(batch.students.all()).order_by("-is_active", "full_name")
    ctx = {"batch": batch, "gap": gap, "students": students, "data": analytics.batch_detail_data(batch),
           "tests": batch.assessments.select_related("mentor").order_by("-scheduled_at")[:10],
           "reason_form": DelayReasonForm(), "mentors": batch.mentors.all()}
    return render(request, "portal/batches_detail.html", ctx)


@require_POST
@role_required(*ALL_ROLES)
def batches_reason(request, pk):
    batch = get_scoped_or_404(analytics.batches_for(request.user), pk)
    gap = analytics.batch_gap(batch)
    form = DelayReasonForm(request.POST)
    if not gap["is_overdue"]:
        messages.info(request, "This batch is not overdue for a test.")
    elif form.is_valid():
        BatchDelayReason.objects.update_or_create(
            batch=batch, expected_date=gap["next_expected"],
            defaults={"reason": form.cleaned_data["reason"], "recorded_by": request.user})
        messages.success(request, "Reason recorded. The alert stays open until a test is completed.")
    else:
        messages.error(request, "Please enter a reason.")
    return redirect("batches_detail", pk=batch.pk)
