from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from accounts.forms import validate_profile_image
from accounts.models import AuditLog, User

from .base import PW, Base, make_user


class LoginAndRoles(Base):
    def post_login(self, user):
        return self.client.post(reverse("login"), {"username": user.username, "password": PW})

    def test_role_based_redirect(self):
        for user, name in [(self.admin, "control_center"), (self.manager, "overview"), (self.m1, "workspace")]:
            self.client.logout()
            self.assertRedirects(self.post_login(user), reverse(name), fetch_redirect_response=False)

    def test_wrong_password_shows_error(self):
        r = self.client.post(reverse("login"), {"username": "mentor1", "password": "nope"})
        self.assertContains(r, "Incorrect username or password")

    def test_inactive_user_cannot_login(self):
        self.m1.is_active = False
        self.m1.save()
        self.assertEqual(self.post_login(self.m1).status_code, 200)

    def test_logout_requires_post(self):
        self.login(self.m1)
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("workspace")).status_code, 302)

    def test_superuser_is_always_admin_even_with_wrong_stored_role(self):
        su = User.objects.create_superuser("root", "r@example.com", PW, role="MENTOR")
        su.refresh_from_db()
        self.assertEqual(su.role, "ADMIN")
        self.assertEqual(su.effective_role, "ADMIN")
        self.login(su)
        self.assertContains(self.client.get(reverse("control_center")), "Admin Control Center")

    def test_sidebar_identity_is_dynamic(self):
        self.login(self.m1)
        html = self.client.get(reverse("workspace")).content.decode()
        self.assertIn("Mentor1", html)
        self.assertNotIn("Admin Control Center", html)
        self.login(self.admin)
        html = self.client.get(reverse("overview")).content.decode()
        self.assertIn("Admin1", html)
        self.assertIn("Admin Control Center", html)


class ControlCenterAccess(Base):
    def test_only_admin_reaches_control_center(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("control_center")).status_code, 302)   # to login
        for user in (self.m1, self.manager):
            self.login(user)
            for name in ("control_center", "users_new"):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403, (user, name))
            self.assertEqual(self.client.post(reverse("users_toggle", args=[self.m2.pk])).status_code, 403)
            self.assertEqual(self.client.get(reverse("users_edit", args=[self.m2.pk])).status_code, 403)
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse("control_center")).status_code, 200)

    def test_django_admin_alias_redirects_to_protected_center(self):
        self.login(self.m1)
        r = self.client.get("/django-admin/", follow=True)
        self.assertEqual(r.status_code, 403)

    def test_raw_django_admin_blocked_for_non_superusers(self):
        for user in (self.admin, self.manager, self.m1):
            self.login(user)
            self.assertNotEqual(self.client.get("/django-admin-raw/").status_code, 200)

    def test_admin_cannot_deactivate_self(self):
        self.login(self.admin)
        self.client.post(reverse("users_toggle", args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_admin_can_toggle_other_and_audit_is_written(self):
        self.login(self.admin)
        self.client.post(reverse("users_toggle", args=[self.m1.pk]))
        self.m1.refresh_from_db()
        self.assertFalse(self.m1.is_active)
        self.assertTrue(AuditLog.objects.filter(action="Deactivated account", target="mentor1").exists())

    def test_search_users(self):
        self.login(self.admin)
        r = self.client.get(reverse("control_center"), {"q": "mentor2"})
        self.assertContains(r, "mentor2")
        self.assertNotContains(r, "manager1@example.com")


class TemporaryPasswordFlow(Base):
    TEMP = "Tr1cky-Temp#778"

    def create(self, role="MENTOR", username="newbie"):
        return self.client.post(reverse("users_new"), {
            "username": username, "first_name": "New", "last_name": "Bie", "email": f"{username}@example.com",
            "role": role, "is_active": "on", "temp_password": self.TEMP})

    def test_full_first_login_flow(self):
        self.login(self.admin)
        self.assertRedirects(self.create(), reverse("control_center"), fetch_redirect_response=False)
        u = User.objects.get(username="newbie")
        self.assertTrue(u.must_change_password)
        self.assertNotIn(self.TEMP, u.password)                 # stored hashed
        self.assertTrue(u.check_password(self.TEMP))
        self.assertFalse(u.is_staff or u.is_superuser)

        self.client.logout()
        self.client.post(reverse("login"), {"username": "newbie", "password": self.TEMP})
        r = self.client.get(reverse("workspace"))               # blocked until password changed
        self.assertRedirects(r, reverse("change_password"), fetch_redirect_response=False)

        weak = self.client.post(reverse("change_password"), {"old_password": self.TEMP, "new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(weak.status_code, 200)                 # validators reject it
        same = self.client.post(reverse("change_password"), {"old_password": self.TEMP, "new_password1": self.TEMP, "new_password2": self.TEMP})
        self.assertEqual(same.status_code, 200)
        ok = self.client.post(reverse("change_password"), {"old_password": self.TEMP, "new_password1": "Brand-New#9921x", "new_password2": "Brand-New#9921x"})
        self.assertRedirects(ok, reverse("workspace"), fetch_redirect_response=False)
        u.refresh_from_db()
        self.assertFalse(u.must_change_password)
        self.assertEqual(self.client.get(reverse("workspace")).status_code, 200)

    def test_existing_users_are_not_forced(self):
        self.login(self.m1)
        self.assertEqual(self.client.get(reverse("workspace")).status_code, 200)

    def test_temp_password_never_echoed(self):
        self.login(self.admin)
        r = self.client.post(reverse("users_new"), {"username": "x y", "temp_password": self.TEMP})   # invalid form re-rendered
        self.assertNotContains(r, self.TEMP)

    def test_admin_can_create_each_role_and_extra_fields_cannot_escalate(self):
        self.login(self.admin)
        for role in ("ADMIN", "MANAGEMENT", "MENTOR"):
            self.create(role, f"u_{role.lower()}")
            self.assertEqual(User.objects.get(username=f"u_{role.lower()}").role, role)
        self.client.post(reverse("users_new"), {"username": "sneaky", "first_name": "S", "email": "s@e.com", "role": "MENTOR",
                                                "temp_password": self.TEMP, "is_superuser": "on", "is_staff": "on"})
        s = User.objects.get(username="sneaky")
        self.assertFalse(s.is_superuser or s.is_staff)

    def test_admin_cannot_change_own_role(self):
        self.login(self.admin)
        r = self.client.post(reverse("users_edit", args=[self.admin.pk]), {"first_name": "A", "email": "a@e.com", "role": "MENTOR", "is_active": "on"})
        self.assertEqual(r.status_code, 200)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, "ADMIN")


class ImageValidation(Base):
    def test_rejects_non_image_and_wrong_extension_and_oversize(self):
        with self.assertRaises(ValidationError):
            validate_profile_image(SimpleUploadedFile("a.png", b"not an image", content_type="image/png"))
        with self.assertRaises(ValidationError):
            validate_profile_image(SimpleUploadedFile("a.exe", b"x" * 10))
        with self.assertRaises(ValidationError):
            validate_profile_image(SimpleUploadedFile("a.png", b"x" * (3 * 1024 * 1024)))

    def test_accepts_real_png(self):
        import io
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (4, 4), "red").save(buf, "PNG")
        f = SimpleUploadedFile("ok.png", buf.getvalue(), content_type="image/png")
        self.assertIs(validate_profile_image(f), f)
