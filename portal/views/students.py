from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render

from accounts.models import User
from accounts.permissions import ALL_ROLES, STAFF, role_required

from .. import analytics
from ..forms import StudentForm
from ..models import Batch
from .helpers import get_scoped_or_404, paginate


@role_required(*ALL_ROLES)
def students_list(request):
    qs = analytics.students_for(request.user).select_related("batch")
    q = request.GET.get("q", "").strip()
    batch, mentor, status = request.GET.get("batch", ""), request.GET.get("mentor", ""), request.GET.get("status", "active")
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(student_code__icontains=q) | Q(email__icontains=q))
    if batch.isdigit():
        qs = qs.filter(batch_id=int(batch))
    if mentor.isdigit() and request.user.is_staff_role:
        qs = qs.filter(batch__in=Batch.objects.filter(mentors__pk=int(mentor)))
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    qs = analytics.annotate_students(qs).order_by("batch__name", "full_name")
    if request.GET.get("attention") == "1":
        threshold = settings.TF_ATTENTION_THRESHOLD
        qs = qs.filter(avg_pct__lt=threshold)
    ctx = {"page": paginate(request, qs), "q": q, "batch": batch, "mentor": mentor, "status": status,
           "attention": request.GET.get("attention") == "1",
           "batches": analytics.batches_for(request.user), "mentors": analytics.active_mentors() if request.user.is_staff_role else None}
    return render(request, "portal/students_list.html", ctx)


@role_required(*STAFF)
def students_new(request):
    form = StudentForm(request.POST or None, initial={"batch": request.GET.get("batch")})
    if request.method == "POST" and form.is_valid():
        s = form.save()
        messages.success(request, f"Student {s.full_name} added.")
        return redirect("students_detail", pk=s.pk)
    return render(request, "portal/form.html", {"form": form, "title": "Add student", "back": "students_list"})


@role_required(*STAFF)
def students_edit(request, pk):
    student = get_scoped_or_404(analytics.students_for(request.user), pk)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Student updated.")
        return redirect("students_detail", pk=student.pk)
    return render(request, "portal/form.html", {"form": form, "title": f"Edit {student.full_name}", "back": "students_list"})


@role_required(*ALL_ROLES)
def students_detail(request, pk):
    # Scoped queryset: a mentor asking for a student outside their batches gets 404, not the data.
    student = get_scoped_or_404(analytics.students_for(request.user).select_related("batch"), pk)
    stats = analytics.student_stats(student)
    return render(request, "portal/students_detail.html", {"student": student, "s": stats,
                                                           "mentors": student.batch.mentors.all(), "can_edit": request.user.is_staff_role})
