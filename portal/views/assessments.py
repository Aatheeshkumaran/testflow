import calendar
from datetime import date, datetime

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import ALL_ROLES, role_required

from .. import analytics, services
from ..forms import (AssessmentFilterForm, AssessmentForm, CancelForm, CompleteForm, RescheduleForm, parse_marks)
from ..models import PENDING_STATUSES, Assessment
from .helpers import get_scoped_or_404, paginate


def _filtered(request):
    qs = analytics.assessments_for(request.user).select_related("batch", "mentor").annotate(n_res=Count("results", distinct=True))
    form = AssessmentFilterForm(request.GET or None, user=request.user)
    if form.is_valid():
        d = form.cleaned_data
        if d.get("q"):
            qs = qs.filter(Q(title__icontains=d["q"]) | Q(subject__icontains=d["q"]))
        if d.get("batch"):
            qs = qs.filter(batch=d["batch"])
        if d.get("mentor"):
            qs = qs.filter(mentor=d["mentor"])
        if d.get("date_from"):
            qs = qs.filter(scheduled_at__date__gte=d["date_from"])
        if d.get("date_to"):
            qs = qs.filter(scheduled_at__date__lte=d["date_to"])
        st = d.get("status")
        if st == "MISSED":
            today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
            qs = qs.filter(status__in=PENDING_STATUSES, scheduled_at__lt=today_start)
        elif st:
            qs = qs.filter(status=st)
    return qs, form


def _month_grid(qs, year, month):
    first = date(year, month, 1)
    items = {}
    for a in qs.filter(scheduled_at__date__gte=first, scheduled_at__date__lte=date(year, month, calendar.monthrange(year, month)[1])):
        items.setdefault(timezone.localtime(a.scheduled_at).date(), []).append(a)
    weeks = [[{"date": d, "in_month": d.month == month, "items": items.get(d, []), "today": d == timezone.localdate()} for d in week]
             for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)]
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    return {"weeks": weeks, "label": first.strftime("%B %Y"), "prev": f"{prev_y}-{prev_m:02d}", "next": f"{next_y}-{next_m:02d}"}


@role_required(*ALL_ROLES)
def tests_list(request):
    qs, form = _filtered(request)
    view = request.GET.get("view", "list")
    ctx = {"form": form, "view": view}
    if view == "calendar":
        try:
            y, m = map(int, request.GET.get("month", "").split("-"))
            date(y, m, 1)
        except ValueError:
            y, m = timezone.localdate().year, timezone.localdate().month
        ctx["cal"] = _month_grid(qs, y, m)
    else:
        ctx["page"] = paginate(request, qs.order_by("-scheduled_at"))
    return render(request, "portal/tests_list.html", ctx)


@role_required(*ALL_ROLES)
def tests_new(request):
    form = AssessmentForm(request.POST or None, user=request.user, initial={"batch": request.GET.get("batch")})
    if request.method == "POST" and form.is_valid():
        a = form.save(commit=False)
        a.created_by = request.user
        if request.user.is_mentor_role:
            a.mentor = request.user
        a.save()
        services.record_created(a, request.user)
        messages.success(request, "Test scheduled.")
        return redirect("tests_detail", pk=a.pk)
    return render(request, "portal/form.html", {"form": form, "title": "Schedule a test", "back": "tests_list"})


@role_required(*ALL_ROLES)
def tests_edit(request, pk):
    a = get_scoped_or_404(analytics.assessments_for(request.user), pk)
    if not analytics.can_edit_assessment(request.user, a):
        raise PermissionDenied("Only the responsible mentor, Management or Admin can edit this test.")
    form = AssessmentForm(request.POST or None, instance=a, user=request.user)
    if request.method == "POST" and form.is_valid():
        old_time = Assessment.objects.get(pk=a.pk).scheduled_at
        obj = form.save()
        services.log_event(obj, request.user, "EDITED", old=old_time if old_time != obj.scheduled_at else None,
                           new=obj.scheduled_at if old_time != obj.scheduled_at else None)
        messages.success(request, "Test updated.")
        return redirect("tests_detail", pk=a.pk)
    return render(request, "portal/form.html", {"form": form, "title": f"Edit {a.title}", "back": "tests_list"})


@role_required(*ALL_ROLES)
def tests_detail(request, pk):
    a = get_scoped_or_404(analytics.assessments_for(request.user).select_related("batch", "mentor", "created_by"), pk)
    results = a.results.select_related("student", "entered_by")
    active = a.batch.students.filter(is_active=True).count()
    ctx = {"a": a, "results": results, "events": a.events.select_related("actor"), "active_students": active,
           "can_edit": analytics.can_edit_assessment(request.user, a), "complete_form": CompleteForm(),
           "cancel_form": CancelForm(), "reschedule_form": RescheduleForm(),
           "class_avg": results.aggregate(v=Avg("percentage"))["v"]}
    return render(request, "portal/tests_detail.html", ctx)


@require_POST
@role_required(*ALL_ROLES)
def tests_action(request, pk):
    a = get_scoped_or_404(analytics.assessments_for(request.user).select_related("batch", "mentor"), pk)
    if not analytics.can_edit_assessment(request.user, a):
        raise PermissionDenied("Only the responsible mentor, Management or Admin can change this test.")
    action = request.POST.get("action")
    try:
        if action == "complete":
            f = CompleteForm(request.POST)
            if not f.is_valid():
                raise services.ServiceError("Check the start/end times.")
            services.complete_assessment(a, request.user, f.cleaned_data.get("actual_start"), f.cleaned_data.get("actual_end"))
            messages.success(request, "Marked as completed. Now enter the marks.")
            return redirect("tests_marks", pk=a.pk)
        if action == "cancel":
            f = CancelForm(request.POST)
            if not f.is_valid():
                raise services.ServiceError("A reason is required to cancel a test.")
            services.cancel_assessment(a, request.user, f.cleaned_data["reason"])
            messages.success(request, "Test cancelled and Management notified.")
        elif action == "reschedule":
            f = RescheduleForm(request.POST)
            if not f.is_valid():
                raise services.ServiceError("Enter a new date/time and a reason.")
            services.reschedule_assessment(a, request.user, f.cleaned_data["new_time"], f.cleaned_data["reason"])
            messages.success(request, "Test rescheduled and Management notified.")
        else:
            raise services.ServiceError("Unknown action.")
    except services.ServiceError as exc:
        messages.error(request, str(exc))
    return redirect("tests_detail", pk=a.pk)


@role_required(*ALL_ROLES)
def tests_marks(request, pk):
    """One grid for the whole class: marks + feedback per active student. All-or-nothing validation."""
    a = get_scoped_or_404(analytics.assessments_for(request.user).select_related("batch", "mentor"), pk)
    if not analytics.can_edit_assessment(request.user, a):
        raise PermissionDenied("Only the responsible mentor, Management or Admin can enter marks.")
    if a.status != Assessment.Status.COMPLETED:
        messages.error(request, "Mark the test as completed before entering marks.")
        return redirect("tests_detail", pk=a.pk)
    existing = {r.student_id: r for r in a.results.all()}
    rows, errors, parsed = [], False, []
    for s in a.batch.students.filter(is_active=True).order_by("full_name"):
        raw = request.POST.get(f"marks_{s.pk}", "" if request.method == "POST" else (f"{existing[s.pk].marks_obtained:g}" if s.pk in existing else ""))
        fb = request.POST.get(f"feedback_{s.pk}", "" if request.method == "POST" else (existing[s.pk].feedback if s.pk in existing else ""))
        err = None
        if request.method == "POST":
            value, err = parse_marks(raw, a.max_marks)
            if err:
                errors = True
            elif value is not None:
                parsed.append((s, value, fb.strip()))
        rows.append({"student": s, "marks": raw, "feedback": fb, "error": err, "saved": s.pk in existing})
    if request.method == "POST" and not errors:
        if not parsed:
            messages.error(request, "Enter marks for at least one student.")
        else:
            try:
                services.save_marks(a, request.user, parsed)
                messages.success(request, f"Saved {len(parsed)} result(s).")
                return redirect("tests_detail", pk=a.pk)
            except services.ServiceError as exc:
                messages.error(request, str(exc))
    elif errors:
        messages.error(request, "Fix the highlighted marks and save again. Nothing was saved.")
    return render(request, "portal/tests_marks.html", {"a": a, "rows": rows})
