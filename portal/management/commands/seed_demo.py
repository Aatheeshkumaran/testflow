"""Development-only demo data so every chart has something to show. Refuses to run when DEBUG is off."""
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from portal import services
from portal.models import Assessment, AssessmentResult, Batch, MentorTask, Student

DEMO_PASSWORD = "Demo@12345"


class Command(BaseCommand):
    help = "Create demo users, batches, students, tests and marks (DEBUG only). Use --confirm to proceed."

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs when TESTFLOW_DEBUG=1.")
        if not opts["confirm"]:
            raise CommandError("This adds demo records. Re-run with --confirm to proceed.")
        if User.objects.filter(username="demo_mentor1").exists():
            raise CommandError("Demo data already exists; nothing was changed.")
        rnd = random.Random(7)
        now = timezone.now()

        def mk(username, first, last, role):
            u = User(username=username, first_name=first, last_name=last, email=f"{username}@example.com", role=role)
            u.set_password(DEMO_PASSWORD)
            u.save()
            return u

        mk("demo_admin", "Asha", "Admin", "ADMIN")
        mgr = mk("demo_manager", "Meera", "Manager", "MANAGEMENT")
        mentors = [mk("demo_mentor1", "Karthik", "R", "MENTOR"), mk("demo_mentor2", "Divya", "S", "MENTOR"), mk("demo_mentor3", "Arun", "P", "MENTOR")]
        subjects = ["Python", "SQL", "Django", "JavaScript"]
        batches = []
        for i, (name, mentor, interval) in enumerate([("Batch A", mentors[0], 7), ("Batch B", mentors[1], 7), ("Batch C", mentors[2], 10)]):
            b = Batch.objects.create(name=name, course="Full-stack", start_date=(now - timedelta(days=120)).date(), test_interval_days=interval)
            b.mentors.add(mentor)
            batches.append(b)
            for n in range(1, 9):
                Student.objects.create(student_code=f"{name[-1]}{n:03d}", full_name=f"Student {name[-1]}{n}", email=f"s{name[-1]}{n}@example.com",
                                       batch=b, joined_on=(now - timedelta(days=120)).date())
        # Mentor 1 is diligent, mentor 2 is patchy, mentor 3 has stopped testing.
        plan = {0: (14, 0.0), 1: (7, 0.35), 2: (3, 0.5)}
        for idx, b in enumerate(batches):
            mentor = mentors[idx]
            count, skip = plan[idx]
            for k in range(count):
                when = now - timedelta(days=(count - k) * 7 + rnd.randint(0, 2) + (30 if idx == 2 else 0))
                a = Assessment.objects.create(title=f"{subjects[k % 4]} Test {k + 1}", batch=b, subject=subjects[k % 4], mentor=mentor, created_by=mentor,
                                              scheduled_at=when, results_due_at=when + timedelta(days=2))
                if rnd.random() < skip:
                    services.cancel_assessment(a, mentor, "Trainer unavailable")
                    continue
                services.complete_assessment(a, mentor)
                if idx == 1 and k == count - 1:
                    continue   # leave marks missing on mentor 2's latest test
                base = rnd.randint(45, 85)
                for s in b.students.all():
                    AssessmentResult.objects.create(assessment=a, student=s, marks_obtained=Decimal(max(0, min(100, base + rnd.randint(-25, 15)))), max_marks=Decimal(100), entered_by=mentor)
        MentorTask.objects.create(title="Update curriculum tracker", assigned_to=mentors[0], created_by=mgr, deadline=now + timedelta(days=3), priority="MEDIUM")
        MentorTask.objects.create(title="Submit feedback summary", assigned_to=mentors[1], created_by=mgr, deadline=now - timedelta(days=2), priority="HIGH")
        MentorTask.objects.create(title="Prepare mock interview slots", assigned_to=mentors[2], created_by=mgr)
        services.sync_alerts(force=True)
        self.stdout.write(self.style.SUCCESS(f"Demo data created. Logins: demo_admin / demo_manager / demo_mentor1..3, password {DEMO_PASSWORD}"))
