from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from portal import analytics, services
from portal.models import Assessment, AssessmentResult, MentorTask, Notification
from portal.views.helpers import csv_safe

from .base import Base, make_user


class Scoping(Base):
    """Mentors see only their own responsibility; enforced by the backend, not by hidden links."""

    def setUp(self):
        super().setUp()
        self.a2 = self.make_assessment(self.b2, self.m2, 3)
        self.result(self.a2, self.s2, 80)

    def test_mentor_cannot_open_other_students_tests_batches(self):
        self.login(self.m1)
        for name, pk in [("students_detail", self.s2.pk), ("tests_detail", self.a2.pk), ("batches_detail", self.b2.pk),
                         ("tests_marks", self.a2.pk), ("students_edit", self.s2.pk)]:
            self.assertIn(self.client.get(reverse(name, args=[pk])).status_code, (403, 404), name)

    def test_mentor_lists_are_filtered(self):
        self.login(self.m1)
        r = self.client.get(reverse("students_list"))
        self.assertContains(r, "Asha One")
        self.assertNotContains(r, "Bala Two")
        self.assertNotContains(self.client.get(reverse("tests_list")), self.a2.title + "</b>")

    def test_staff_only_pages_forbidden_for_mentor(self):
        self.login(self.m1)
        for name in ("overview", "mentors_list", "batches_new", "students_new", "tasks_new", "reports_mentors"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)
        self.assertEqual(self.client.get(reverse("mentors_detail", args=[self.m2.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("mentors_detail", args=[self.m1.pk])).status_code, 200)

    def test_management_cannot_use_mentor_workspace_or_control_center(self):
        self.login(self.manager)
        self.assertEqual(self.client.get(reverse("workspace")).status_code, 403)
        self.assertEqual(self.client.get(reverse("control_center")).status_code, 403)
        self.assertEqual(self.client.get(reverse("overview")).status_code, 200)

    def test_mentor_cannot_schedule_for_other_batch_or_as_other_mentor(self):
        self.login(self.m1)
        when = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(reverse("tests_new"), {"title": "X", "batch": self.b2.pk, "subject": "S", "mentor": self.m2.pk,
                                                     "assessment_type": "QUIZ", "mode": "ONLINE", "max_marks": "50", "scheduled_at": when})
        self.assertEqual(r.status_code, 200)                      # form error, nothing created
        self.assertFalse(Assessment.objects.filter(title="X").exists())
        self.client.post(reverse("tests_new"), {"title": "Y", "batch": self.b1.pk, "subject": "S", "mentor": self.m2.pk,
                                                 "assessment_type": "QUIZ", "mode": "ONLINE", "max_marks": "50", "scheduled_at": when})
        self.assertEqual(Assessment.objects.get(title="Y").mentor, self.m1)   # forced to self

    def test_co_mentor_cannot_edit_another_mentors_test(self):
        self.b1.mentors.add(self.m2)
        a = self.make_assessment(self.b1, self.m1, 2)
        self.login(self.m2)
        self.assertEqual(self.client.get(reverse("tests_detail", args=[a.pk])).status_code, 200)   # may view
        self.assertEqual(self.client.get(reverse("tests_marks", args=[a.pk])).status_code, 403)    # may not edit
        self.assertEqual(self.client.post(reverse("tests_action", args=[a.pk]), {"action": "cancel", "reason": "x"}).status_code, 403)

    def test_csv_export_is_scoped_and_safe(self):
        self.login(self.m1)
        self.assertNotContains(self.client.get(reverse("reports_results")), "Bala Two")
        self.login(self.manager)
        self.assertContains(self.client.get(reverse("reports_results")), "Bala Two")
        self.assertEqual(csv_safe("=1+1"), "'=1+1")


class Marks(Base):
    def test_percentage_formula(self):
        a = self.make_assessment(self.b1, self.m1, 2)
        self.assertEqual(self.result(a, self.s1, "45", "60").percentage, Decimal("75.00"))

    def test_database_rules(self):
        a = self.make_assessment(self.b1, self.m1, 2)
        self.result(a, self.s1, 50)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.result(a, self.s1, 60)                          # duplicate result
        a2 = self.make_assessment(self.b1, self.m1, 3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentResult.objects.create(assessment=a2, student=self.s1, marks_obtained=Decimal("101"), max_marks=Decimal("100"), entered_by=self.m1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssessmentResult.objects.create(assessment=a2, student=self.s1, marks_obtained=Decimal("-1"), max_marks=Decimal("100"), entered_by=self.m1)

    def test_marks_grid_validates_and_saves_all_or_nothing(self):
        s1b = self.s1.__class__.objects.create(student_code="A002", full_name="Second", batch=self.b1)
        a = self.make_assessment(self.b1, self.m1, 1)
        self.login(self.m1)
        url = reverse("tests_marks", args=[a.pk])
        bad = self.client.post(url, {f"marks_{self.s1.pk}": "80", f"marks_{s1b.pk}": "150"})
        self.assertContains(bad, "Cannot exceed")
        self.assertEqual(a.results.count(), 0)
        self.client.post(url, {f"marks_{self.s1.pk}": "80", f"marks_{s1b.pk}": "", f"feedback_{self.s1.pk}": "good"})
        self.assertEqual(a.results.count(), 1)
        self.client.post(url, {f"marks_{self.s1.pk}": "90", f"marks_{s1b.pk}": "40"})     # edit + add, still no duplicates
        self.assertEqual(a.results.count(), 2)
        self.assertEqual(a.results.get(student=self.s1).percentage, Decimal("90.00"))

    def test_marks_require_completed_test(self):
        a = self.make_assessment(self.b1, self.m1, 1, status="SCHEDULED")
        self.login(self.m1)
        self.assertRedirects(self.client.get(reverse("tests_marks", args=[a.pk])), reverse("tests_detail", args=[a.pk]))


class Lifecycle(Base):
    def test_complete_cancel_reschedule_rules(self):
        future = self.make_assessment(self.b1, self.m1, -3, status="SCHEDULED")
        with self.assertRaises(services.ServiceError):
            services.complete_assessment(future, self.m1)       # cannot complete a future test
        with self.assertRaises(services.ServiceError):
            services.cancel_assessment(future, self.m1, "  ")   # reason required
        services.reschedule_assessment(future, self.m1, timezone.now() + timedelta(days=9), "Holiday")
        future.refresh_from_db()
        self.assertEqual((future.status, future.reschedule_count), ("RESCHEDULED", 1))
        services.cancel_assessment(future, self.m1, "Trainer ill")
        self.assertEqual(future.events.count(), 2)
        self.assertTrue(Notification.objects.filter(recipient=self.manager, kind="TEST_CHANGED").exists())
        with self.assertRaises(services.ServiceError):
            services.complete_assessment(future, self.m1)       # cancelled is not completable

    def test_completed_sets_marks_deadline(self):
        a = self.make_assessment(self.b1, self.m1, 1, status="SCHEDULED")
        services.complete_assessment(a, self.m1)
        a.refresh_from_db()
        self.assertEqual(a.status, "COMPLETED")
        self.assertEqual(a.results_due_at, a.scheduled_at + timedelta(days=2))


class Tasks(Base):
    def make(self, **kw):
        return MentorTask.objects.create(title="T", assigned_to=self.m1, created_by=self.manager, **kw)

    def test_overdue_rules(self):
        now = timezone.now()
        self.assertFalse(self.make().is_overdue)                                           # no deadline
        self.assertTrue(self.make(deadline=now - timedelta(days=1)).is_overdue)
        self.assertFalse(self.make(deadline=now + timedelta(days=1)).is_overdue)
        done = self.make(deadline=now - timedelta(days=1), status="COMPLETED", completed_at=now - timedelta(days=2))
        self.assertFalse(done.is_overdue)
        self.assertTrue(done.completed_on_time)

    def test_workflow_and_permissions(self):
        self.login(self.manager)
        r = self.client.post(reverse("tasks_new"), {"title": "Plan", "assigned_to": self.m1.pk, "priority": "HIGH"})
        task = MentorTask.objects.get(title="Plan")
        self.assertTrue(Notification.objects.filter(recipient=self.m1, kind="TASK_ASSIGNED").exists())
        self.assertEqual(self.client.post(reverse("tasks_detail", args=[task.pk]), {"status": "COMPLETED", "progress": 5, "note": "x"}).status_code, 403)
        self.login(self.m2)
        self.assertEqual(self.client.get(reverse("tasks_detail", args=[task.pk])).status_code, 404)    # not theirs
        self.login(self.m1)
        self.client.post(reverse("tasks_detail", args=[task.pk]), {"status": "COMPLETED", "progress": 10, "note": "done"})
        task.refresh_from_db()
        self.assertEqual((task.status, task.progress), ("COMPLETED", 100))
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.updates.count(), 1)
        self.assertTrue(Notification.objects.filter(recipient=self.manager, kind="TASK_DONE").exists())

    def test_blocked_needs_note(self):
        t = self.make()
        self.login(self.m1)
        r = self.client.post(reverse("tasks_detail", args=[t.pk]), {"status": "BLOCKED", "progress": 10, "note": " "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(t.updates.count(), 0)


class Alerts(Base):
    def count(self, kind):
        return Notification.objects.filter(kind=kind, resolved_at__isnull=True).count()

    def test_batch_gap_alert_is_deduplicated_and_resolves(self):
        gap = analytics.batch_gap(self.b1)
        self.assertTrue(gap["is_overdue"])
        services.sync_alerts(force=True)
        first = self.count("BATCH_GAP")
        self.assertGreater(first, 0)
        services.sync_alerts(force=True)
        self.assertEqual(self.count("BATCH_GAP"), first)         # no duplicates for the same unresolved issue
        self.assertTrue(Notification.objects.filter(recipient=self.m1, kind="BATCH_GAP").exists())
        self.assertFalse(Notification.objects.filter(recipient=self.m1, kind="BATCH_GAP", title__contains="B2").exists())
        for b, m in ((self.b1, self.m1), (self.b2, self.m2)):
            self.make_assessment(b, m, 0)                                # a completed test today satisfies the rule
        services.sync_alerts(force=True)
        self.assertEqual(self.count("BATCH_GAP"), 0)

    def test_reason_does_not_clear_alert_but_is_shown(self):
        self.login(self.m1)
        self.client.post(reverse("batches_reason", args=[self.b1.pk]), {"reason": "Exams week"})
        self.assertEqual(analytics.batch_gap(self.b1)["reason"].reason, "Exams week")
        self.assertTrue(analytics.batch_gap(self.b1)["is_overdue"])

    def test_missed_and_marks_and_task_alerts(self):
        missed = self.make_assessment(self.b1, self.m1, 5, status="SCHEDULED")
        done = self.make_assessment(self.b1, self.m1, 6)                 # completed, no marks, deadline passed
        MentorTask.objects.create(title="Late", assigned_to=self.m1, created_by=self.manager, deadline=timezone.now() - timedelta(days=1))
        services.sync_alerts(force=True)
        for kind in ("TEST_MISSED", "MARKS_MISSING", "TASK_OVERDUE"):
            self.assertGreater(self.count(kind), 0, kind)
        services.complete_assessment(missed, self.m1)
        self.result(missed, self.s1, 70)
        self.result(done, self.s1, 70)
        MentorTask.objects.update(status="COMPLETED")
        services.sync_alerts(force=True)
        for kind in ("TEST_MISSED", "MARKS_MISSING", "TASK_OVERDUE"):
            self.assertEqual(self.count(kind), 0, kind)

    def test_notification_recipient_restrictions(self):
        services.sync_alerts(force=True)
        n = Notification.objects.filter(recipient=self.m1).first()
        self.login(self.m2)
        self.assertEqual(self.client.post(reverse("notifications_read", args=[n.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("notifications_open", args=[n.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("notifications")), n.title)
        self.login(self.m1)
        self.client.get(reverse("notifications_open", args=[n.pk]))
        n.refresh_from_db()
        self.assertTrue(n.is_read)


class Metrics(Base):
    def test_conduct_rate_denominators_and_ranking(self):
        self.make_assessment(self.b1, self.m1, 10)
        self.make_assessment(self.b1, self.m1, 9)
        self.make_assessment(self.b1, self.m1, 8, status="CANCELLED", outcome_reason="x")
        self.make_assessment(self.b1, self.m1, 7, status="SCHEDULED")                    # missed
        self.make_assessment(self.b1, self.m1, -4, status="SCHEDULED")                   # future: not "due"
        m = analytics.mentor_metrics(self.m1)
        self.assertEqual((m["due"], m["conducted"], m["cancelled"], m["missed"], m["upcoming"]), (4, 2, 1, 1, 1))
        self.assertEqual(m["conduct"], 50)
        self.assertEqual(m["marks"], 0)                                          # 0 of 2 completed tests have marks
        self.assertIsNone(m["task_rate"])                                        # no tasks -> no data, not 0%
        self.assertTrue(m["ranked"])
        self.assertIsNotNone(m["score"])

    def test_insufficient_data_is_not_ranked_and_zero_denominators_are_safe(self):
        m = analytics.mentor_metrics(self.m2)
        self.assertIsNone(m["conduct"])
        self.assertIsNone(m["marks"])
        self.assertFalse(m["ranked"])
        self.assertIsNone(m["score"])

    def test_leaderboard_sorts_ranked_first(self):
        for d in (9, 8, 7):
            self.make_assessment(self.b1, self.m1, d)
        rows = analytics.leaderboard()
        self.assertEqual(rows[0]["mentor"], self.m1)
        self.assertEqual(rows[0]["rank"], 1)
        self.assertNotIn("rank", rows[-1])

    def test_student_stats_and_attention(self):
        for d, pct in ((9, 40), (6, 35), (3, 30)):
            self.result(self.make_assessment(self.b1, self.m1, d), self.s1, pct)
        st = analytics.student_stats(self.s1)
        self.assertEqual(st["average"], 35.0)
        self.assertEqual(st["count"], 3)
        self.assertTrue(st["attention"])
        self.assertIsNone(st["batch_avg"])                                       # one student only: no misleading comparison
        self.assertEqual([r["student"] for r in analytics.students_needing_attention(self.m1)], [self.s1])
        self.assertEqual(analytics.students_needing_attention(self.m2), [])

    def test_org_counts(self):
        self.make_assessment(self.b1, self.m1, 3)
        c = analytics.org_counts()
        self.assertEqual((c["students"], c["mentors"], c["management"], c["assessments"], c["completed"]), (2, 2, 1, 1, 1))


class PagesRender(Base):
    """Smoke-render every page with real data and with none (empty states)."""

    def test_empty_states_render(self):
        for user, names in [(self.manager, ["overview", "mentors_list", "batches_list", "students_list", "tests_list", "tasks_list", "notifications", "reports"]),
                            (self.m1, ["workspace", "batches_list", "students_list", "tests_list", "tasks_list"]),
                            (self.admin, ["control_center", "users_new"])]:
            self.login(user)
            for n in names:
                self.assertEqual(self.client.get(reverse(n)).status_code, 200, (user.username, n))
        self.login(self.manager)
        self.assertEqual(self.client.get(reverse("students_detail", args=[self.s1.pk])).status_code, 200)

    def test_pages_render_with_data(self):
        for d in (12, 8, 4):
            for b, m, s in ((self.b1, self.m1, self.s1), (self.b2, self.m2, self.s2)):
                self.result(self.make_assessment(b, m, d), s, 50 + d)
        self.make_assessment(self.b1, self.m1, -2, status="SCHEDULED")
        self.make_assessment(self.b1, self.m1, 1, status="CANCELLED", outcome_reason="Power cut")
        MentorTask.objects.create(title="Report", assigned_to=self.m1, created_by=self.manager, deadline=timezone.now() - timedelta(days=1))
        services.sync_alerts(force=True)
        a = Assessment.objects.filter(batch=self.b1).first()
        paths = [reverse("overview"), reverse("overview") + "?days=0", reverse("mentors_list"), reverse("mentors_detail", args=[self.m1.pk]),
                 reverse("batches_detail", args=[self.b1.pk]), reverse("students_detail", args=[self.s1.pk]),
                 reverse("tests_list") + "?view=calendar", reverse("tests_list") + "?status=MISSED", reverse("tests_detail", args=[a.pk]),
                 reverse("tasks_list") + "?status=OVERDUE", reverse("reports_tests"), reverse("reports_mentors"), reverse("notifications")]
        self.login(self.manager)
        for p in paths:
            self.assertEqual(self.client.get(p).status_code, 200, p)
        self.login(self.m1)
        for p in (reverse("workspace"), reverse("mentors_detail", args=[self.m1.pk]), reverse("students_detail", args=[self.s1.pk]),
                  reverse("tests_detail", args=[a.pk]), reverse("tests_marks", args=[Assessment.objects.filter(batch=self.b1, status="COMPLETED").first().pk])):
            self.assertEqual(self.client.get(p).status_code, 200, p)
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("control_center")).status_code, 200)

    def test_student_chart_data_is_real(self):
        a = self.make_assessment(self.b1, self.m1, 3)
        self.result(a, self.s1, 64)
        self.login(self.m1)
        self.assertContains(self.client.get(reverse("students_detail", args=[self.s1.pk])), "64.0")
