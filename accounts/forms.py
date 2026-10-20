import io

from django import forms
from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import PasswordChangeForm
from PIL import Image

from .models import User

ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}


def validate_profile_image(f):
    """Size limit, extension allow-list, and a real decode with Pillow (not just trusting the filename)."""
    if f is None:
        return f
    limit = settings.TF_MAX_UPLOAD_MB * 1024 * 1024
    if f.size > limit:
        raise forms.ValidationError(f"Image is too large (max {settings.TF_MAX_UPLOAD_MB} MB).")
    ext = f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
    if ext not in ALLOWED_EXT:
        raise forms.ValidationError("Use a JPG, PNG or WEBP image.")
    try:
        data = f.read()
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise forms.ValidationError("That file is not a valid image.")
    finally:
        f.seek(0)
    return f


class UserCreateForm(forms.ModelForm):
    temp_password = forms.CharField(label="Temporary password", widget=forms.PasswordInput(render_value=False),
                                    help_text="The user must replace this at first login. It is never shown again.")

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "profile_image", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["first_name"].required = True
        self.fields["is_active"].initial = True

    def clean_profile_image(self):
        return validate_profile_image(self.cleaned_data.get("profile_image"))

    def clean(self):
        data = super().clean()
        pw = data.get("temp_password")
        if pw:
            probe = User(username=data.get("username", ""), first_name=data.get("first_name", ""),
                         last_name=data.get("last_name", ""), email=data.get("email", ""))
            try:
                password_validation.validate_password(pw, probe)
            except forms.ValidationError as exc:
                self.add_error("temp_password", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["temp_password"])  # hashed; plaintext is discarded
        user.must_change_password = True
        user.is_staff = False       # TestFlow roles never grant Django-admin access
        user.is_superuser = False
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    new_temp_password = forms.CharField(label="Reset password (optional)", required=False,
                                        widget=forms.PasswordInput(render_value=False),
                                        help_text="Leave blank to keep the current password. A reset forces a change at next login.")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "profile_image", "is_active"]

    def __init__(self, *args, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["email"].required = True
        if self.instance.is_superuser:
            self.fields["role"].disabled = True   # superusers are always Admin

    def clean_profile_image(self):
        return validate_profile_image(self.cleaned_data.get("profile_image"))

    def clean(self):
        data = super().clean()
        if self.actor and self.instance.pk == self.actor.pk:
            if not data.get("is_active", True):
                self.add_error("is_active", "You cannot deactivate your own account.")
            if data.get("role") and data["role"] != self.instance.role and not self.instance.is_superuser:
                self.add_error("role", "You cannot change your own role.")
        pw = data.get("new_temp_password")
        if pw:
            try:
                password_validation.validate_password(pw, self.instance)
            except forms.ValidationError as exc:
                self.add_error("new_temp_password", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get("new_temp_password")
        if pw:
            user.set_password(pw)
            user.must_change_password = True
        if commit:
            user.save()
        return user


class ForcedPasswordChangeForm(PasswordChangeForm):
    """Django's validators apply; additionally the new password must differ from the old one."""

    def clean(self):
        cleaned = super().clean()
        old, new = cleaned.get("old_password"), cleaned.get("new_password1")
        if old and new and old == new:
            self.add_error("new_password1", "Choose a password different from your current one.")
        return cleaned