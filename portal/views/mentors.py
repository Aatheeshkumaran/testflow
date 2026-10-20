from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render

from accounts.models import User
from accounts.permissions import ALL_ROLES, STAFF, role_required

from .. import analytics
from ..models import Batch


@role_required(*STAFF)
def mentors_list(request):
    days, since = analytics.period_since(request.GET.get("days"))
    batch = Batch.objects.filter(pk=request.GET.get("batch")).first() if request.GET.get("batch") else None
    board = analytics.leaderboard(since, batch)
    ctx = {"board": board, "days": days, "batch": batch, "batches": Batch.objects.all(),
           "charts": analytics.mentor_charts(board) if board else None, "weights": analytics.SCORE_WEIGHTS}
    return render(request, "portal/mentors_list.html", ctx)


@role_required(*ALL_ROLES)
def mentors_detail(request, pk):
    mentor = get_object_or_404(User, pk=pk, role=User.Role.MENTOR, is_superuser=False)
    if request.user.is_mentor_role and request.user.pk != mentor.pk:
        raise PermissionDenied("Mentors can only open their own scorecard.")
    days, since = analytics.period_since(request.GET.get("days"))
    ctx = {"mentor_obj": mentor, "days": days, "m": analytics.mentor_metrics(mentor, since),
           "data": analytics.mentor_detail_data(mentor, since), "weights": analytics.SCORE_WEIGHTS,
           "batches": mentor.batches.filter(is_active=True),
           "attention_students": analytics.students_needing_attention(mentor)}
    return render(request, "portal/mentors_detail.html", ctx)
