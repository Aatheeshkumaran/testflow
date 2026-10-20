"""Read-only metrics. Every percentage is computed here, with the denominator stated, so it is easy to audit.

Rates return None when the denominator is zero ("no data"), never 0% and never 100%.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db.models import Avg, Count, Max, OuterRef, Q, Subquery
from django.db.models.functions import TruncMonth
from django.utils import timezone

from accounts.models import User

from . import charts
from .models import PENDING_STATUSES, Assessment, AssessmentResult, Batch, MentorTask, Student

A = Assessment.Status
SCORE_WEIGHTS = {"conduct": 30, "marks": 20, "compliance": 20, "task_rate": 15, "on_time": 15}


def rate(numerator, denominator):
    return round(numerator * 100 / denominator) if denominator else None


def avg(value, nd=1):
    return round(float(value), nd) if value is not None else None


def period_since(raw):
    """GET ?days=30|90|365|0 -> (days, since_datetime). Default 90 days; 0 = all time."""
    try:
        days = int(raw)
    except (TypeError, ValueError):
        days = 90
    if days not in (30, 90, 180, 365, 0):
        days = 90
    return days, (timezone.now() - timedelta(days=days) if days else None)


# ------------------------------------------------------------------------- scoping (the permission core)
def batches_for(user):
    qs = Batch.objects.all()
    return qs.filter(mentors=user) if user.is_mentor_role else qs


def students_for(user):
    if user.is_mentor_role:
        return Student.objects.filter(batch__in=Batch.objects.filter(mentors=user))
    return Student.objects.all()


def assessments_for(user):
    if user.is_mentor_role:
        return Assessment.objects.filter(Q(batch__in=Batch.objects.filter(mentors=user)) | Q(mentor=user))
    return Assessment.objects.all()


def tasks_for(user):
    return MentorTask.objects.filter(assigned_to=user) if user.is_mentor_role else MentorTask.objects.all()


def can_edit_assessment(user, assessment):
    return user.is_staff_role or (user.is_mentor_role and assessment.mentor_id == user.id)


def active_mentors():
    return User.objects.filter(is_active=True, role=User.Role.MENTOR, is_superuser=False).order_by("first_name", "username")


# ------------------------------------------------------------------------- counts
def org_counts():
    now = timezone.now()
    users = User.objects.filter(is_active=True)
    return {
        "active_users": users.count(),
        "students": Student.objects.filter(is_active=True).count(),
        "mentors": users.filter(role=User.Role.MENTOR, is_superuser=False).count(),
        "management": users.filter(role=User.Role.MANAGEMENT, is_superuser=False).count(),
        "admins": users.filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True)).count(),
        "assessments": Assessment.objects.count(),
        "completed": Assessment.objects.filter(status=A.COMPLETED).count(),
        "open_tasks": MentorTask.objects.exclude(status=MentorTask.Status.COMPLETED).count(),
        "overdue_tasks": MentorTask.objects.filter(deadline__lt=now).exclude(status=MentorTask.Status.COMPLETED).count(),
    }


def _active_student_counts():
    return dict(Student.objects.filter(is_active=True).values_list("batch").annotate(c=Count("id")))


def assessments_missing_marks(qs=None):
    """Completed tests where fewer results exist than active students in the batch."""
    qs = Assessment.objects.all() if qs is None else qs
    qs = qs.filter(status=A.COMPLETED).annotate(n_res=Count("results")).select_related("batch", "mentor")
    active = _active_student_counts()
    return [a for a in qs if a.n_res < active.get(a.batch_id, 0)]


# ------------------------------------------------------------------------- batch test-frequency rule
def batch_gap(batch, today=None):
    """When was the last completed test, when is the next one due (batch.test_interval_days), how late are we?"""
    today = today or timezone.localdate()
    last = batch.assessments.filter(status=A.COMPLETED).order_by("-scheduled_at").first()
    if last:
        base = timezone.localtime(last.actual_end or last.scheduled_at).date()
    else:
        base = batch.start_date or timezone.localtime(batch.created_at).date()
    next_expected = base + timedelta(days=batch.test_interval_days)
    days_late = max((today - next_expected).days, 0)
    upcoming = batch.assessments.filter(status__in=PENDING_STATUSES, scheduled_at__gte=timezone.now()).order_by("scheduled_at").first()
    reason = batch.delay_reasons.filter(expected_date=next_expected).first()
    return {"batch": batch, "last": last, "last_date": base if last else None, "next_expected": next_expected,
            "days_late": days_late, "is_overdue": days_late > 0, "next_scheduled": upcoming, "reason": reason}


def live_batches():
    today = timezone.localdate()
    return Batch.objects.filter(is_active=True).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))


def batch_gaps(batches=None, only_overdue=False):
    batches = live_batches() if batches is None else batches
    rows = [batch_gap(b) for b in batches.prefetch_related("mentors")]
    return [r for r in rows if r["is_overdue"]] if only_overdue else rows


# ------------------------------------------------------------------------- mentor accountability
def mentor_metrics(mentor, since=None, batch=None):
    """Scorecard for one mentor.

    conduct    = completed / due                (due = scheduled date has passed; cancelled + missed count against)
    marks      = fully-entered / completed      (fully entered = results for every active student in the batch)
    compliance = batches within their test interval / active batches
    task_rate  = completed tasks / tasks assigned in period
    on_time    = completed by deadline / tasks that have a deadline and are completed or overdue
    score      = weighted mean of the metrics that have data (weights in SCORE_WEIGHTS); None if not enough data.
    """
    now = timezone.now()
    qs = Assessment.objects.filter(mentor=mentor)
    if since:
        qs = qs.filter(scheduled_at__gte=since)
    if batch:
        qs = qs.filter(batch=batch)
    due = qs.filter(scheduled_at__lte=now)
    due_total = due.count()
    completed_qs = due.filter(status=A.COMPLETED)
    conducted = completed_qs.count()
    cancelled = due.filter(status=A.CANCELLED).count()
    missed = due.filter(status__in=PENDING_STATUSES).count()
    rescheduled = qs.filter(reschedule_count__gt=0).count()
    upcoming = qs.filter(status__in=PENDING_STATUSES, scheduled_at__gt=now).count()

    active = _active_student_counts()
    done_list = list(completed_qs.annotate(n_res=Count("results")))
    marks_ok = sum(1 for a in done_list if a.n_res >= active.get(a.batch_id, 0))
    marks_pending = conducted - marks_ok

    tasks = MentorTask.objects.filter(assigned_to=mentor)
    if since:
        tasks = tasks.filter(created_at__gte=since)
    task_list = list(tasks)
    t_total = len(task_list)
    t_done = sum(1 for t in task_list if not t.is_open)
    t_overdue = sum(1 for t in task_list if t.is_overdue)
    dl = [t for t in task_list if t.deadline and (not t.is_open or t.is_overdue)]
    t_ontime = sum(1 for t in dl if t.completed_on_time)

    my_batches = live_batches().filter(mentors=mentor)
    if batch:
        my_batches = my_batches.filter(pk=batch.pk)
    gaps = [batch_gap(b) for b in my_batches]
    compliant = sum(1 for g in gaps if not g["is_overdue"])

    avg_score = completed_qs.aggregate(v=Avg("results__percentage"))["v"]
    m = {
        "mentor": mentor,
        "students": students_for(mentor).filter(is_active=True).count(),
        "batches": len(gaps), "due": due_total, "conducted": conducted, "cancelled": cancelled, "missed": missed,
        "rescheduled": rescheduled, "upcoming": upcoming, "marks_pending": marks_pending,
        "tasks_total": t_total, "tasks_done": t_done, "tasks_overdue": t_overdue,
        "avg_score": avg(avg_score),
        "conduct": rate(conducted, due_total), "marks": rate(marks_ok, conducted),
        "compliance": rate(compliant, len(gaps)), "task_rate": rate(t_done, t_total), "on_time": rate(t_ontime, len(dl)),
        "gap_batches": [g for g in gaps if g["is_overdue"]],
    }
    available = {k: m[k] for k in SCORE_WEIGHTS if m[k] is not None}
    m["ranked"] = due_total >= settings.TF_MIN_TESTS_FOR_RANKING and bool(available)
    m["score"] = round(sum(SCORE_WEIGHTS[k] * v for k, v in available.items()) / sum(SCORE_WEIGHTS[k] for k in available)) if m["ranked"] else None
    return m


def leaderboard(since=None, batch=None):
    rows = [mentor_metrics(m, since, batch) for m in active_mentors()]
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["mentor"].display_name))
    for i, r in enumerate([r for r in rows if r["ranked"]], start=1):
        r["rank"] = i
    return rows


def mentor_monitor_rows():
    """Daily 'is every mentor conducting tests?' table for Management."""
    now = timezone.now()
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today_start.replace(day=1)
    gaps = batch_gaps(only_overdue=True)
    missing = assessments_missing_marks()
    rows = []
    for m in active_mentors():
        mine = Assessment.objects.filter(mentor=m)
        last = mine.filter(status=A.COMPLETED).aggregate(v=Max("scheduled_at"))["v"]
        nxt = mine.filter(status__in=PENDING_STATUSES, scheduled_at__gte=now).order_by("scheduled_at").first()
        missed = mine.filter(status__in=PENDING_STATUSES, scheduled_at__lt=today_start).count()
        my_gaps = [g for g in gaps if m.id in {x.id for x in g["batch"].mentors.all()}]
        my_missing = [a for a in missing if a.mentor_id == m.id]
        has_batches = m.batches.filter(is_active=True).exists()
        if missed or my_gaps or my_missing:
            status = "attention"
        elif last is None:
            status = "no_tests" if has_batches else "no_batches"
        else:
            status = "ok"
        rows.append({
            "mentor": m, "last_test": last, "days_since": (timezone.localdate() - timezone.localtime(last).date()).days if last else None,
            "this_month": mine.filter(status=A.COMPLETED, scheduled_at__gte=month_start).count(),
            "next_test": nxt, "missed": missed, "gaps": my_gaps, "marks_pending": len(my_missing), "status": status,
        })
    order = {"attention": 0, "no_tests": 1, "no_batches": 2, "ok": 3}
    rows.sort(key=lambda r: (order[r["status"]], r["mentor"].display_name))
    return rows


# ------------------------------------------------------------------------- organisation / management charts
def org_overview(since=None):
    now = timezone.now()
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    qs = Assessment.objects.all()
    if since:
        qs = qs.filter(scheduled_at__gte=since)
    status = {
        "Completed": qs.filter(status=A.COMPLETED).count(),
        "Cancelled": qs.filter(status=A.CANCELLED).count(),
        "Missed (no outcome)": qs.filter(status__in=PENDING_STATUSES, scheduled_at__lt=today_start).count(),
        "Upcoming": qs.filter(status__in=PENDING_STATUSES, scheduled_at__gte=today_start).count(),
    }
    res = AssessmentResult.objects.all()
    if since:
        res = res.filter(assessment__scheduled_at__gte=since)

    months = (res.annotate(m=TruncMonth("assessment__scheduled_at")).values("m").annotate(a=Avg("percentage")).order_by("m"))
    month_rows = list(months)[-12:]
    batch_rows = (res.values("assessment__batch__name").annotate(a=Avg("percentage"), n=Count("student", distinct=True)).order_by("-a"))
    batch_rows = list(batch_rows)
    return {
        "status": status,
        "completed": status["Completed"],
        "missed": status["Missed (no outcome)"],
        "avg_score": avg(res.aggregate(v=Avg("percentage"))["v"]),
        "results_count": res.count(),
        "charts": {
            "status": charts.doughnut_chart(list(status), list(status.values()), [charts.GREEN, charts.RED, charts.AMBER, charts.SLATE]),
            "monthly": charts.line_chart([r["m"].strftime("%b %Y") for r in month_rows], [{"label": "Average score", "data": [r["a"] for r in month_rows]}]),
            "batches": charts.bar_chart([f'{r["assessment__batch__name"]} ({r["n"]})' for r in batch_rows],
                                        [{"label": "Average score", "data": [r["a"] for r in batch_rows]}], percent=True),
        },
    }


def mentor_charts(rows):
    """Comparison charts across mentors, from leaderboard rows."""
    names = [r["mentor"].display_name for r in rows]
    return {
        "tests": charts.bar_chart(names, [
            {"label": "Conducted", "data": [r["conducted"] for r in rows], "color": charts.GREEN},
            {"label": "Cancelled", "data": [r["cancelled"] for r in rows], "color": charts.RED},
            {"label": "Missed", "data": [r["missed"] for r in rows], "color": charts.AMBER}], stacked=True),
        "rates": charts.bar_chart(names, [
            {"label": "Conducted %", "data": [r["conduct"] for r in rows], "color": charts.VIOLET},
            {"label": "Marks entered %", "data": [r["marks"] for r in rows], "color": charts.SKY},
            {"label": "Tasks done %", "data": [r["task_rate"] for r in rows], "color": charts.NAVY}], percent=True),
    }


def mentor_detail_data(mentor, since=None):
    now = timezone.now()
    qs = Assessment.objects.filter(mentor=mentor)
    if since:
        qs = qs.filter(scheduled_at__gte=since)
    months = {}
    for a in qs.filter(scheduled_at__lte=now):
        key = timezone.localtime(a.scheduled_at).strftime("%Y-%m")
        d = months.setdefault(key, {"c": 0, "x": 0, "m": 0})
        d["c" if a.status == A.COMPLETED else "x" if a.status == A.CANCELLED else "m"] += 1
    keys = sorted(months)[-12:]
    label = lambda k: datetime.strptime(k, "%Y-%m").strftime("%b %Y")
    scored = (qs.filter(status=A.COMPLETED).annotate(a=Avg("results__percentage"), n=Count("results"))
              .filter(n__gt=0).order_by("scheduled_at"))
    scored = list(scored)[-15:]
    tasks = list(MentorTask.objects.filter(assigned_to=mentor))
    t = {"Completed": sum(1 for x in tasks if not x.is_open), "Overdue": sum(1 for x in tasks if x.is_overdue),
         "In progress / pending": sum(1 for x in tasks if x.is_open and not x.is_overdue)}
    return {
        "charts": {
            "monthly": charts.bar_chart([label(k) for k in keys], [
                {"label": "Conducted", "data": [months[k]["c"] for k in keys], "color": charts.GREEN},
                {"label": "Cancelled", "data": [months[k]["x"] for k in keys], "color": charts.RED},
                {"label": "Missed", "data": [months[k]["m"] for k in keys], "color": charts.AMBER}], stacked=True),
            "scores": charts.line_chart([f'{timezone.localtime(a.scheduled_at):%d %b} · {a.title[:18]}' for a in scored],
                                        [{"label": "Class average", "data": [a.a for a in scored]}]),
            "tasks": charts.doughnut_chart(list(t), list(t.values()), [charts.GREEN, charts.RED, charts.SLATE]),
        },
        "recent": qs.select_related("batch").order_by("-scheduled_at")[:10],
        "has_scores": bool(scored),
    }


# ------------------------------------------------------------------------- students
def annotate_students(qs):
    latest = AssessmentResult.objects.filter(student=OuterRef("pk")).order_by("-assessment__scheduled_at")
    return qs.annotate(
        avg_pct=Avg("results__percentage"), test_count=Count("results"),
        latest_pct=Subquery(latest.values("percentage")[:1]),
        last_test=Subquery(latest.values("assessment__scheduled_at")[:1]),
    )


def student_stats(student):
    results = list(student.results.select_related("assessment").order_by("assessment__scheduled_at"))
    pcts = [float(r.percentage) for r in results]
    n = len(results)
    average = round(sum(pcts) / n, 1) if n else None
    prev = pcts[:-1]
    trend = round(pcts[-1] - sum(prev) / len(prev), 1) if prev else None

    subjects = {}
    for r in results:
        subjects.setdefault(r.assessment.subject, []).append(float(r.percentage))
    subject_rows = sorted(({"subject": s, "avg": round(sum(v) / len(v), 1), "n": len(v)} for s, v in subjects.items()), key=lambda x: x["avg"])
    threshold = settings.TF_ATTENTION_THRESHOLD
    weak = [s for s in subject_rows if s["avg"] < threshold]

    aids = [r.assessment_id for r in results]
    per_test = {x["assessment_id"]: float(x["a"]) for x in
                AssessmentResult.objects.filter(assessment_id__in=aids).values("assessment_id").annotate(a=Avg("percentage"), c=Count("id"))
                if x["c"] >= settings.TF_MIN_BATCH_SAMPLE}
    batch_agg = AssessmentResult.objects.filter(student__batch=student.batch).aggregate(a=Avg("percentage"), s=Count("student", distinct=True))
    batch_avg = avg(batch_agg["a"]) if batch_agg["s"] >= settings.TF_MIN_BATCH_SAMPLE else None

    missing = Assessment.objects.filter(batch=student.batch, status=A.COMPLETED, scheduled_at__date__gte=student.joined_on).exclude(id__in=aids)

    reasons = []
    last3 = pcts[-3:]
    if last3 and sum(last3) / len(last3) < threshold:
        reasons.append(f"Last {len(last3)} test average is below {threshold}%")
    if trend is not None and trend <= -15:
        reasons.append(f"Latest score dropped {abs(trend)} points below earlier average")
    for s in weak:
        reasons.append(f"Weak in {s['subject']} ({s['avg']}%)")

    labels = [f'{timezone.localtime(r.assessment.scheduled_at):%d %b} · {r.assessment.title[:18]}' for r in results]
    datasets = [{"label": "Student", "data": pcts}]
    if per_test:
        datasets.append({"label": "Batch average", "data": [per_test.get(r.assessment_id) for r in results], "color": charts.SLATE, "dashed": True, "points": 2})
    return {
        "results": list(reversed(results)), "count": n, "average": average, "latest": results[-1] if results else None,
        "trend": trend, "subjects": subject_rows, "weak": weak, "batch_avg": batch_avg, "missing": missing,
        "attention": reasons, "has_data": n > 0,
        "charts": {
            "trend": charts.line_chart(labels, datasets),
            "subjects": charts.bar_chart([s["subject"] for s in subject_rows], [{"label": "Average", "data": [s["avg"] for s in subject_rows]}], percent=True, horizontal=True),
        },
    }


def students_needing_attention(user, limit=8):
    """Active students (in the user's scope) whose last 3 results average below the threshold."""
    rows = []
    threshold = settings.TF_ATTENTION_THRESHOLD
    for s in students_for(user).filter(is_active=True).select_related("batch"):
        last = list(s.results.order_by("-assessment__scheduled_at").values_list("percentage", flat=True)[:3])
        if last and sum(float(x) for x in last) / len(last) < threshold:
            rows.append({"student": s, "avg": round(sum(float(x) for x in last) / len(last), 1), "n": len(last)})
    rows.sort(key=lambda r: r["avg"])
    return rows[:limit]


def batch_detail_data(batch):
    tests = list(batch.assessments.filter(status=A.COMPLETED).annotate(a=Avg("results__percentage"), n=Count("results")).filter(n__gt=0).order_by("scheduled_at"))[-15:]
    return {
        "chart": charts.line_chart([f'{timezone.localtime(t.scheduled_at):%d %b} · {t.title[:18]}' for t in tests], [{"label": "Class average", "data": [t.a for t in tests]}]),
        "has_data": bool(tests),
    }
