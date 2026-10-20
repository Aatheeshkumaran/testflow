from django.shortcuts import render
from django.utils import timezone

from accounts.permissions import STAFF, R, role_required

from .. import analytics, services
from ..models import Assessment, MentorTask


@role_required(*STAFF)
def overview(request):
    """Management / Admin overview. The 'is every mentor conducting tests?' monitor lives here."""
    services.sync_alerts()
    days, since = analytics.period_since(request.GET.get("days"))
    board = analytics.leaderboard(since)
    data = analytics.org_overview(since)
    now = timezone.now()
    ctx = {
        "days": days, "counts": analytics.org_counts(), "monitor": analytics.mentor_monitor_rows(),
        "gaps": analytics.batch_gaps(only_overdue=True), "missing_marks": analytics.assessments_missing_marks()[:8],
        "board": board, "overview": data, "mentor_charts": analytics.mentor_charts(board) if board else None,
        "attention_students": analytics.students_needing_attention(request.user),
        "upcoming": Assessment.objects.select_related("batch", "mentor").filter(status__in=("SCHEDULED", "RESCHEDULED"), scheduled_at__gte=now).order_by("scheduled_at")[:6],
        "overdue_tasks": [t for t in MentorTask.objects.select_related("assigned_to").exclude(status="COMPLETED").filter(deadline__lt=now)][:6],
    }
    return render(request, "portal/overview.html", ctx)


@role_required(R.MENTOR)
def workspace(request):
    services.sync_alerts()
    user = request.user
    now = timezone.now()
    mine = analytics.assessments_for(user).select_related("batch", "mentor")
    metrics = analytics.mentor_metrics(user, since=None)
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    ctx = {
        "metrics": metrics,
        "gaps": analytics.batch_gaps(analytics.batches_for(user).filter(is_active=True)),
        "upcoming": mine.filter(status__in=("SCHEDULED", "RESCHEDULED"), scheduled_at__gte=today_start).order_by("scheduled_at")[:6],
        "to_close": mine.filter(mentor=user, status__in=("SCHEDULED", "RESCHEDULED"), scheduled_at__lt=today_start).order_by("scheduled_at")[:6],
        "missing_marks": analytics.assessments_missing_marks(mine.filter(mentor=user))[:6],
        "tasks": MentorTask.objects.filter(assigned_to=user).exclude(status="COMPLETED").order_by("deadline", "-created_at")[:6],
        "attention_students": analytics.students_needing_attention(user),
        "student_count": analytics.students_for(user).filter(is_active=True).count(),
    }
    return render(request, "portal/workspace.html", ctx)
