from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.RoleAwareLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),   # POST only (Django 5)
    path("", views.home, name="home"),
    path("account/change-password/", views.change_password, name="change_password"),
    path("control-center/", views.control_center, name="control_center"),
    path("control-center/users/new/", views.user_create, name="users_new"),
    path("control-center/users/<int:pk>/edit/", views.user_edit, name="users_edit"),
    path("control-center/users/<int:pk>/toggle/", views.user_toggle, name="users_toggle"),
]
