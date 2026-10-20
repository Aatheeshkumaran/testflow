from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Users with must_change_password=True can only reach the password page, logout, static and media."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.must_change_password:
            allowed = (reverse("change_password"), reverse("logout"))
            exempt_prefixes = ("/" + settings.STATIC_URL.lstrip("/"), settings.MEDIA_URL)
            if request.path not in allowed and not request.path.startswith(exempt_prefixes):
                return redirect("change_password")
        return self.get_response(request)
