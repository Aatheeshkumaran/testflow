from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from portal.models import Assessment, AssessmentResult, Batch, MentorTask, Student

PW = "Str0ng-Test#4471"


def make_user(username, role, **kw):
    return User.objects.create_user(username=username, password=PW, role=role, first_name=username.title(),
                                    email=f"{username}@example.com", **kw)


class Base(TestCase):
    """Two mentors with their own batch + student, one manager, one admin."""

    def setUp(self):
        self.admin = make_user("admin1", "ADMIN")
        self.manager = make_user("manager1", "MANAGEMENT")
        self.m1 = make_user("mentor1", "MENTOR")
        self.m2 = make_user("mentor2", "MENTOR")
        self.b1 = Batch.objects.create(name="B1", start_date=timezone.localdate() - timedelta(days=30), test_interval_days=7)
        self.b2 = Batch.objects.create(name="B2", start_date=timezone.localdate() - timedelta(days=30), test_interval_days=7)
        self.b1.mentors.add(self.m1)
        self.b2.mentors.add(self.m2)
        self.s1 = Student.objects.create(student_code="a001", full_name="Asha One", batch=self.b1)
        self.s2 = Student.objects.create(student_code="b001", full_name="Bala Two", batch=self.b2)

    def login(self, user):
        self.client.logout()
        self.assertTrue(self.client.login(username=user.username, password=PW))

    def make_assessment(self, batch, mentor, days_ago, status="COMPLETED", **kw):
        when = timezone.now() - timedelta(days=days_ago)
        return Assessment.objects.create(title=f"T{days_ago}", batch=batch, subject="Python", mentor=mentor, created_by=mentor,
                                         scheduled_at=when, status=status, results_due_at=when + timedelta(days=2), **kw)

    def result(self, a, student, marks, mx=100):
        return AssessmentResult.objects.create(assessment=a, student=student, marks_obtained=Decimal(marks), max_marks=Decimal(mx), entered_by=a.mentor)
