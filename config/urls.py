from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    # Developer-only Django admin (requires is_staff; only superusers are ever given it).
    path("django-admin-raw/", admin.site.urls),
    # Old alias now simply points to the custom Admin Control Center.
    path("django-admin/", RedirectView.as_view(pattern_name="control_center", permanent=False)),
    path("", include("accounts.urls")),
    path("", include("portal.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler403 = "accounts.views.permission_denied"
