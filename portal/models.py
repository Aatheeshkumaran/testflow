from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

U = settings.AUTH_USER_MODEL


class Batch(models.Model):
    """A group of students. Responsibility: a Mentor sees only batches they are attached to."""
    name = models.CharField(max_length=100, unique=True)
    course = models.CharField(max_length=150, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    mentors = models.ManyToManyField(U, related_name="batches", blank=True, limit_choices_to={"role": "MENTOR"})
    test_interval_days = models.PositiveSmallIntegerField(
        default=7, validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text="A test should be conducted at least this often (in days). Used for missed-test alerts.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "batches"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})

    def __str__(self):
        return self.name


class Student(models.Model):
    student_code = models.CharField(max_length=30, unique=True)
    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="students")
    joined_on = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["batch__name", "full_name"]
        indexes = [models.Index(fields=["batch", "is_active"])]

    def save(self, *args, **kwargs):
        self.student_code = self.student_code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.student_code})"


PENDING_STATUSES = ("SCHEDULED", "RESCHEDULED")


class Assessment(models.Model):
    """One test. `mentor` is the person accountable for conducting it."""

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"

    class Mode(models.TextChoices):
        IN_PERSON = "IN_PERSON", "In person"
        ONLINE = "ONLINE", "Online"
        HYBRID = "HYBRID", "Hybrid"

    class Type(models.TextChoices):
        QUIZ = "QUIZ", "Quiz"
        PRACTICAL = "PRACTICAL", "Practical"
        ASSIGNMENT = "ASSIGNMENT", "Assignment"
        MOCK_TEST = "MOCK_TEST", "Mock test"
        PROJECT_REVIEW = "PROJECT_REVIEW", "Project review"
        OTHER = "OTHER", "Other"

    title = models.CharField(max_length=200)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="assessments")
    subject = models.CharField(max_length=150)
    mentor = models.ForeignKey(U, on_delete=models.PROTECT, related_name="conducted_assessments")
    created_by = models.ForeignKey(U, on_delete=models.PROTECT, related_name="created_assessments")
    assessment_type = models.CharField(max_length=20, choices=Type.choices, default=Type.QUIZ)
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.IN_PERSON)
    venue = models.CharField(max_length=200, blank=True)
    max_marks = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("100"),
                                    validators=[MinValueValidator(Decimal("0.01"))])
    scheduled_at = models.DateTimeField()
    actual_start = models.DateTimeField(null=True, blank=True)
    actual_end = models.DateTimeField(null=True, blank=True)
    results_due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    reschedule_count = models.PositiveSmallIntegerField(default=0)
    outcome_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"]), models.Index(fields=["mentor", "status"])]

    def clean(self):
        if self.status in (self.Status.CANCELLED, self.Status.RESCHEDULED) and not self.outcome_reason.strip():
            raise ValidationError({"outcome_reason": "A reason is required for cancelled or rescheduled tests."})
        if self.actual_start and self.actual_end and self.actual_end < self.actual_start:
            raise ValidationError({"actual_end": "End time cannot be before start time."})

    @property
    def is_pending(self):
        return self.status in PENDING_STATUSES

    @property
    def is_overdue(self):
        """Still pending although its date has passed = missed so far."""
        return self.is_pending and self.scheduled_at < timezone.now()

    def __str__(self):
        return f"{self.title} — {self.batch}"


class AssessmentEvent(models.Model):
    """Audit trail of everything that happens to a test."""
    class Action(models.TextChoices):
        CREATED = "CREATED", "Scheduled"
        EDITED = "EDITED", "Edited"
        COMPLETED = "COMPLETED", "Marked completed"
        CANCELLED = "CANCELLED", "Cancelled"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"
        MARKS = "MARKS", "Marks entered"

    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(U, null=True, on_delete=models.SET_NULL, related_name="assessment_events")
    action = models.CharField(max_length=20, choices=Action.choices)
    reason = models.TextField(blank=True)
    old_time = models.DateTimeField(null=True, blank=True)
    new_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AssessmentResult(models.Model):
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT, related_name="results")
    student = models.ForeignKey(Student, on_delete=models.PROTECT, related_name="results")
    marks_obtained = models.DecimalField(max_digits=7, decimal_places=2)
    max_marks = models.DecimalField(max_digits=7, decimal_places=2)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, editable=False, default=Decimal("0"))
    feedback = models.TextField(blank=True)
    entered_by = models.ForeignKey(U, on_delete=models.PROTECT, related_name="entered_results")
    entered_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(fields=["assessment", "student"], name="one_result_per_student_per_test"),
            models.CheckConstraint(check=Q(max_marks__gt=0), name="result_max_marks_positive"),
            models.CheckConstraint(check=Q(marks_obtained__gte=0), name="result_marks_not_negative"),
            models.CheckConstraint(check=Q(marks_obtained__lte=models.F("max_marks")), name="result_marks_within_max"),
        ]

    def clean(self):
        if self.max_marks is not None and self.max_marks <= 0:
            raise ValidationError({"max_marks": "Maximum marks must be greater than zero."})
        if self.marks_obtained is not None and self.marks_obtained < 0:
            raise ValidationError({"marks_obtained": "Marks cannot be negative."})
        if None not in (self.marks_obtained, self.max_marks) and self.marks_obtained > self.max_marks:
            raise ValidationError({"marks_obtained": "Marks cannot exceed the maximum."})

    def save(self, *args, **kwargs):
        # percentage = marks_obtained / max_marks * 100  (stored so averages are a plain SQL AVG)
        self.marks_obtained = Decimal(str(self.marks_obtained))
        self.max_marks = Decimal(str(self.max_marks))
        self.percentage = (self.marks_obtained / self.max_marks * 100).quantize(Decimal("0.01")) if self.max_marks else Decimal("0")
        fields = kwargs.get("update_fields")
        if fields is not None:   # Django's update_or_create saves only named fields; percentage must follow marks
            kwargs["update_fields"] = set(fields) | {"percentage"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} — {self.assessment}: {self.percentage}%"


class BatchDelayReason(models.Model):
    """A reason recorded against a missed-test alert (the 'expected by' date identifies the alert)."""
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT, related_name="delay_reasons")
    expected_date = models.DateField()
    reason = models.TextField()
    recorded_by = models.ForeignKey(U, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["batch", "expected_date"], name="one_reason_per_gap")]


class MentorTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        BLOCKED = "BLOCKED", "Blocked"
        COMPLETED = "COMPLETED", "Completed"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(U, on_delete=models.PROTECT, related_name="assigned_tasks",
                                    limit_choices_to={"role": "MENTOR"})
    created_by = models.ForeignKey(U, on_delete=models.PROTECT, related_name="created_tasks")
    deadline = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    progress = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["assigned_to", "status"])]

    @property
    def is_open(self):
        return self.status != self.Status.COMPLETED

    @property
    def is_overdue(self):
        """Overdue = has a deadline AND not completed AND deadline passed. No deadline is never overdue."""
        return bool(self.deadline and self.is_open and self.deadline < timezone.now())

    @property
    def completed_on_time(self):
        if self.status != self.Status.COMPLETED or not self.deadline or not self.completed_at:
            return None
        return self.completed_at <= self.deadline


class TaskUpdate(models.Model):
    task = models.ForeignKey(MentorTask, on_delete=models.PROTECT, related_name="updates")
    updated_by = models.ForeignKey(U, on_delete=models.PROTECT, related_name="task_updates")
    status = models.CharField(max_length=20, choices=MentorTask.Status.choices)
    progress = models.PositiveSmallIntegerField()
    note = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Notification(models.Model):
    class Kind(models.TextChoices):
        TASK_ASSIGNED = "TASK_ASSIGNED", "Task assigned"
        TASK_OVERDUE = "TASK_OVERDUE", "Task overdue"
        TASK_DONE = "TASK_DONE", "Task completed"
        TEST_MISSED = "TEST_MISSED", "Test not conducted"
        TEST_CHANGED = "TEST_CHANGED", "Test cancelled / rescheduled"
        BATCH_GAP = "BATCH_GAP", "No recent test for batch"
        MARKS_MISSING = "MARKS_MISSING", "Marks not entered"

    recipient = models.ForeignKey(U, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=120, blank=True)
    is_read = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]
        constraints = [
            # An unresolved issue never produces a second alert for the same person.
            models.UniqueConstraint(fields=["recipient", "dedupe_key"], condition=~Q(dedupe_key=""),
                                    name="one_alert_per_issue_per_recipient"),
        ]
