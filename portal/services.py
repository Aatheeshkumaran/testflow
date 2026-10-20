"""Write-side business logic: status changes with audit trail, marks entry, notifications and alert syncing."""
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from . import analytics
from .models import (PENDING_STATUSES, Assessment, AssessmentEvent, AssessmentResult, MentorTask, Notification, TaskUpdate)

A = Assessment.Status
K = Notification.Kind
ALERT_KINDS = (K.TASK_OVERDUE, K.TEST_MISSED, K.MARKS_MISSING, K.BATCH_GAP)


class ServiceError(Exception):
    """Raised for rule violations the UI should show to the user."""


def staff_users():
    return User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(role__in=[User.Role.ADMIN, User.Role.MANAGEMENT]))


def notify(users, kind, title, message="", url="", dedupe_key=""):
    for u in users:
        if not u.is_active:
            continue
        if dedupe_key:
            n, created = Notification.objects.get_or_create(
                recipient=u, dedupe_key=dedupe_key, defaults={"kind": kind, "title": title, "message": message, "url": url})
            if not created and n.resolved_at:      # the same issue came back: reopen instead of duplicating
                n.resolved_at, n.is_read = None, False
                n.save(update_fields=["resolved_at", "is_read"])
        else:
            Notification.objects.create(recipient=u, kind=kind, title=title, message=message, url=url)


def log_event(assessment, actor, action, reason="", old=None, new=None):
    return AssessmentEvent.objects.create(assessment=assessment, actor=actor, action=action, reason=reason, old_time=old, new_time=new)


# ----------------------------------------------------------------------------- assessments
@transaction.atomic
def record_created(assessment, actor):
    log_event(assessment, actor, AssessmentEvent.Action.CREATED, new=assessment.scheduled_at)


@transaction.atomic
def complete_assessment(a, actor, start=None, end=None):
    if not a.is_pending:
        raise ServiceError("Only a scheduled or rescheduled test can be marked completed.")
    if timezone.localtime(a.scheduled_at).date() > timezone.localdate():
        raise ServiceError("This test is scheduled for a future date, so it cannot be completed yet.")
    if start and end and end < start:
        raise ServiceError("End time cannot be before start time.")
    a.status, a.actual_start, a.actual_end, a.outcome_reason = A.COMPLETED, start, end, ""
    a.results_due_at = (end or a.scheduled_at) + timedelta(days=settings.TF_MARKS_GRACE_DAYS)
    a.save()
    log_event(a, actor, AssessmentEvent.Action.COMPLETED)


@transaction.atomic
def cancel_assessment(a, actor, reason):
    if not a.is_pending:
        raise ServiceError("Only a scheduled or rescheduled test can be cancelled.")
    if not reason.strip():
        raise ServiceError("A reason is required to cancel a test.")
    a.status, a.outcome_reason = A.CANCELLED, reason.strip()
    a.save()
    log_event(a, actor, AssessmentEvent.Action.CANCELLED, reason=a.outcome_reason, old=a.scheduled_at)
    notify(staff_users().exclude(pk=actor.pk), K.TEST_CHANGED, f"Test cancelled: {a.title}",
           f"{a.batch} · {a.mentor.display_name}. Reason: {a.outcome_reason}", reverse("tests_detail", args=[a.pk]))


@transaction.atomic
def reschedule_assessment(a, actor, new_time, reason):
    if not a.is_pending:
        raise ServiceError("Only a scheduled or rescheduled test can be rescheduled.")
    if not reason.strip():
        raise ServiceError("A reason is required to reschedule a test.")
    if new_time <= timezone.now():
        raise ServiceError("Pick a new date and time in the future.")
    old = a.scheduled_at
    a.scheduled_at, a.status, a.outcome_reason = new_time, A.RESCHEDULED, reason.strip()
    a.reschedule_count += 1
    a.save()
    log_event(a, actor, AssessmentEvent.Action.RESCHEDULED, reason=a.outcome_reason, old=old, new=new_time)
    notify(staff_users().exclude(pk=actor.pk), K.TEST_CHANGED, f"Test rescheduled: {a.title}",
           f"{a.batch} · {a.mentor.display_name}. Reason: {a.outcome_reason}", reverse("tests_detail", args=[a.pk]))


@transaction.atomic
def save_marks(a, actor, rows):
    """rows: list of (student, marks Decimal, feedback). Existing results are updated, never duplicated."""
    if a.status != A.COMPLETED:
        raise ServiceError("Mark the test as completed before entering marks.")
    for student, marks, feedback in rows:
        AssessmentResult.objects.update_or_create(
            assessment=a, student=student,
            defaults={"marks_obtained": marks, "max_marks": a.max_marks, "feedback": feedback, "entered_by": actor})
    log_event(a, actor, AssessmentEvent.Action.MARKS, reason=f"{len(rows)} result(s) saved")
    sync_alerts(force=True)


# ----------------------------------------------------------------------------- tasks
@transaction.atomic
def task_assigned(task):
    notify([task.assigned_to], K.TASK_ASSIGNED, f"New task: {task.title}",
           f"Assigned by {task.created_by.display_name}" + (f" · due {timezone.localtime(task.deadline):%d %b %Y %H:%M}" if task.deadline else ""),
           reverse("tasks_detail", args=[task.pk]))


@transaction.atomic
def apply_task_update(task, actor, status, progress, note):
    if status == MentorTask.Status.COMPLETED:
        progress = 100
    task.status, task.progress = status, progress
    if status == MentorTask.Status.COMPLETED:
        task.completed_at = task.completed_at or timezone.now()
    else:
        task.completed_at = None
    task.save()
    TaskUpdate.objects.create(task=task, updated_by=actor, status=status, progress=progress, note=note)
    if status == MentorTask.Status.COMPLETED:
        notify([task.created_by], K.TASK_DONE, f"Task completed: {task.title}", f"By {actor.display_name}", reverse("tasks_detail", args=[task.pk]))
    sync_alerts(force=True)


# ----------------------------------------------------------------------------- alerts
def sync_alerts(force=False):
    """Create alerts for current problems (once per issue per person) and resolve alerts whose problem is gone.

    Called from dashboards (throttled) and from `manage.py sync_alerts` (schedule it daily for best results).
    """
    if not force and not cache.add("tf-alert-sync", 1, settings.TF_ALERT_SYNC_SECONDS):
        return False
    now = timezone.now()
    today_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    staff = list(staff_users())
    wanted = {}   # dedupe_key -> (kind, recipients, title, message, url)

    for t in MentorTask.objects.select_related("assigned_to").filter(deadline__lt=now).exclude(status=MentorTask.Status.COMPLETED):
        wanted[f"task-overdue-{t.pk}"] = (K.TASK_OVERDUE, [t.assigned_to] + staff, f"Task overdue: {t.title}",
                                           f"{t.assigned_to.display_name} · was due {timezone.localtime(t.deadline):%d %b %Y}", reverse("tasks_detail", args=[t.pk]))

    for a in Assessment.objects.select_related("batch", "mentor").filter(status__in=PENDING_STATUSES, scheduled_at__lt=today_start):
        days = (timezone.localdate() - timezone.localtime(a.scheduled_at).date()).days
        wanted[f"test-missed-{a.pk}"] = (K.TEST_MISSED, [a.mentor] + staff, f"Test not recorded: {a.title}",
                                          f"{a.batch} · {a.mentor.display_name} · {days} day(s) past the scheduled date", reverse("tests_detail", args=[a.pk]))

    for a in analytics.assessments_missing_marks():
        if a.results_due_at and a.results_due_at < now:
            wanted[f"marks-missing-{a.pk}"] = (K.MARKS_MISSING, [a.mentor] + staff, f"Marks missing: {a.title}",
                                                f"{a.batch} · {a.n_res} result(s) entered; deadline passed", reverse("tests_marks", args=[a.pk]))

    for g in analytics.batch_gaps(only_overdue=True):
        b = g["batch"]
        wanted[f"batch-gap-{b.pk}-{g['next_expected'].isoformat()}"] = (
            K.BATCH_GAP, list(b.mentors.all()) + staff, f"No test for {b.name} in {g['days_late'] + b.test_interval_days} days",
            f"Expected by {g['next_expected']:%d %b %Y} (every {b.test_interval_days} days)", reverse("batches_detail", args=[b.pk]))

    for key, (kind, recipients, title, message, url) in wanted.items():
        notify(recipients, kind, title, message, url, dedupe_key=key)
    Notification.objects.filter(kind__in=ALERT_KINDS, resolved_at__isnull=True).exclude(dedupe_key__in=list(wanted)).update(resolved_at=now, is_read=True)
    return True
