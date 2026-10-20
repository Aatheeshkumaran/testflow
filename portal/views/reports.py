import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import ALL_ROLES, STAFF, role_required

from .. import analytics
from ..models import AssessmentResult
from .helpers import csv_safe


def _csv(name, header, rows):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{name}-{timezone.localdate()}.csv"'
    w = csv.writer(resp)
    w.writerow(header)
    for r in rows:
        w.writerow([csv_safe(c) for c in r])
    return resp


@role_required(*ALL_ROLES)
def reports(request):
    return render(request, "portal/reports.html")


@role_required(*ALL_ROLES)
def reports_results(request):
    """Only results for students the requester is allowed to see."""
    qs = AssessmentResult.objects.filter(student__in=analytics.students_for(request.user)).select_related(
        "student", "student__batch", "assessment", "assessment__mentor").order_by("assessment__scheduled_at", "student__full_name")
    rows = [(r.assessment.scheduled_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d"), r.assessment.title, r.assessment.subject,
             r.student.batch.name, r.student.student_code, r.student.full_name, r.marks_obtained, r.max_marks, r.percentage,
             r.assessment.mentor.display_name, r.feedback) for r in qs]
    return _csv("results", ["Test date", "Test", "Subject", "Batch", "Student ID", "Student", "Marks", "Max", "Percent", "Mentor", "Feedback"], rows)


@role_required(*ALL_ROLES)
def reports_tests(request):
    qs = analytics.assessments_for(request.user).select_related("batch", "mentor").order_by("scheduled_at")
    rows = [(timezone.localtime(a.scheduled_at).strftime("%Y-%m-%d %H:%M"), a.title, a.subject, a.batch.name, a.mentor.display_name,
             a.get_status_display(), a.reschedule_count, a.outcome_reason) for a in qs]
    return _csv("tests", ["Scheduled", "Test", "Subject", "Batch", "Mentor", "Status", "Reschedules", "Reason"], rows)


@role_required(*STAFF)
def reports_mentors(request):
    days, since = analytics.period_since(request.GET.get("days"))
    fmt = lambda v: "n/a" if v is None else v
    rows = [(r["mentor"].display_name, r["students"], r["due"], r["conducted"], r["cancelled"], r["missed"], fmt(r["conduct"]), fmt(r["marks"]),
             fmt(r["compliance"]), fmt(r["task_rate"]), fmt(r["on_time"]), fmt(r["score"])) for r in analytics.leaderboard(since)]
    return _csv("mentor-performance", ["Mentor", "Students", "Tests due", "Conducted", "Cancelled", "Missed", "Conducted %",
                                       "Marks entered %", "Schedule compliance %", "Tasks done %", "Tasks on time %", "Score"], rows)
