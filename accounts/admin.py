from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, User


@admin.register(User)
class TestFlowUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("TestFlow", {"fields": ("role", "profile_image", "must_change_password")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("TestFlow", {"fields": ("role", "email")}),)
    list_display = ("username", "first_name", "last_name", "role", "is_active", "is_superuser")
    list_filter = ("role", "is_active", "is_superuser")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target")
    readonly_fields = ("actor", "action", "target", "detail", "created_at")
