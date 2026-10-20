from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGEMENT = "MANAGEMENT", "Management"
        MENTOR = "MENTOR", "Mentor"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MENTOR)
    profile_image = models.ImageField(upload_to="profiles/", blank=True, null=True)
    must_change_password = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # A superuser is always an Admin. This repairs the old "admin shown as Mentor" bug at the source.
        if self.is_superuser and self.role != self.Role.ADMIN:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    # ---- identity helpers: templates and permission checks use these, never raw `role` ----
    @property
    def effective_role(self):
        return self.Role.ADMIN if self.is_superuser else self.role

    @property
    def role_label(self):
        return self.Role(self.effective_role).label

    @property
    def is_admin_role(self):
        return self.effective_role == self.Role.ADMIN

    @property
    def is_management_role(self):
        return self.effective_role == self.Role.MANAGEMENT

    @property
    def is_mentor_role(self):
        return self.effective_role == self.Role.MENTOR

    @property
    def is_staff_role(self):
        """Admin or Management: organisation-wide visibility."""
        return self.effective_role in (self.Role.ADMIN, self.Role.MANAGEMENT)

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username

    @property
    def initials(self):
        parts = self.display_name.split()
        return "".join(p[0] for p in parts[:2]).upper() or "?"

    def __str__(self):
        return f"{self.display_name} ({self.role_label})"


class AuditLog(models.Model):
    """Record of sensitive administrative actions (account creation, role change, activation...)."""
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_entries")
    action = models.CharField(max_length=60)
    target = models.CharField(max_length=150, blank=True)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} → {self.target}"


def audit(actor, action, target="", detail=""):
    return AuditLog.objects.create(actor=actor, action=action, target=str(target)[:150], detail=detail)
