from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone

from accounts.models import User

from . import analytics
from .models import Assessment, Batch, BatchDelayReason, MentorTask, Student

DT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
D = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def dt_field(**kw):
    return forms.DateTimeField(widget=DT, input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"], **kw)


class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["name", "course", "start_date", "end_date", "mentors", "test_interval_days", "is_active"]
        widgets = {"start_date": D, "end_date": D, "mentors": forms.CheckboxSelectMultiple}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["mentors"].queryset = analytics.active_mentors()


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["student_code", "full_name", "email", "batch", "joined_on", "is_active", "notes"]
        widgets = {"joined_on": D, "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["batch"].queryset = Batch.objects.filter(is_active=True) if not self.instance.pk else Batch.objects.all()

    def clean_student_code(self):
        code = self.cleaned_data["student_code"].strip().upper()
        clash = Student.objects.filter(student_code=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError("A student with this ID already exists.")
        return code


class AssessmentForm(forms.ModelForm):
    scheduled_at = dt_field(label="Date & time")

    class Meta:
        model = Assessment
        fields = ["title", "batch", "subject", "mentor", "assessment_type", "mode", "venue", "max_marks", "scheduled_at", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *a, user, **kw):
        super().__init__(*a, **kw)
        self.user = user
        self.fields["batch"].queryset = analytics.batches_for(user).filter(is_active=True) if not self.instance.pk else analytics.batches_for(user)
        if user.is_mentor_role:
            self.fields["mentor"].queryset = User.objects.filter(pk=user.pk)
            self.fields["mentor"].initial = user.pk
            self.fields["mentor"].disabled = True
        else:
            self.fields["mentor"].queryset = analytics.active_mentors()
        if self.instance.pk and self.instance.results.exists():
            for f in ("batch", "max_marks"):     # results already exist: protect their meaning
                self.fields[f].disabled = True

    def clean(self):
        data = super().clean()
        batch, mentor = data.get("batch"), data.get("mentor")
        if batch and mentor and not batch.mentors.filter(pk=mentor.pk).exists():
            self.add_error("mentor", "This mentor is not assigned to the selected batch.")
        return data


class AssessmentFilterForm(forms.Form):
    q = forms.CharField(required=False)
    status = forms.ChoiceField(required=False, choices=[("", "Any status"), *Assessment.Status.choices, ("MISSED", "Missed (no outcome)")])
    batch = forms.ModelChoiceField(required=False, queryset=Batch.objects.none(), empty_label="All batches")
    mentor = forms.ModelChoiceField(required=False, queryset=User.objects.none(), empty_label="All mentors")
    date_from = forms.DateField(required=False, widget=D)
    date_to = forms.DateField(required=False, widget=D)

    def __init__(self, *a, user, **kw):
        super().__init__(*a, **kw)
        self.fields["batch"].queryset = analytics.batches_for(user)
        self.fields["mentor"].queryset = analytics.active_mentors()
        if user.is_mentor_role:
            del self.fields["mentor"]


class CompleteForm(forms.Form):
    actual_start = dt_field(required=False)
    actual_end = dt_field(required=False)


class CancelForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))


class RescheduleForm(forms.Form):
    new_time = dt_field(label="New date & time")
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))


class DelayReasonForm(forms.ModelForm):
    class Meta:
        model = BatchDelayReason
        fields = ["reason"]
        widgets = {"reason": forms.Textarea(attrs={"rows": 2, "placeholder": "Why has no test been conducted?"})}


class TaskForm(forms.ModelForm):
    deadline = dt_field(required=False, help_text="Optional. Tasks with no deadline are never overdue.")

    class Meta:
        model = MentorTask
        fields = ["title", "description", "assigned_to", "priority", "deadline"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["assigned_to"].queryset = analytics.active_mentors()
        self.fields["assigned_to"].label = "Assign to mentor"


class TaskUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=MentorTask.Status.choices)
    progress = forms.IntegerField(min_value=0, max_value=100, initial=0, help_text="0–100")
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Daily note")

    def clean(self):
        data = super().clean()
        if data.get("status") == MentorTask.Status.BLOCKED and not (data.get("note") or "").strip():
            self.add_error("note", "Please describe what is blocking you.")
        return data


def parse_marks(raw, max_marks):
    """Returns (Decimal|None, error|None). Blank = skip this student."""
    raw = (raw or "").strip()
    if raw == "":
        return None, None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None, "Enter a number."
    if value < 0:
        return None, "Cannot be negative."
    if value > max_marks:
        return None, f"Cannot exceed {max_marks:g}."
    return value.quantize(Decimal("0.01")), None
