# security/api/routers.py
from django.urls import path

from security.api.views.auth import RefreshView, SignInView

from .views.me import MeView
from .views.me_by_id import MeByIdView
from .views.whoami import whoami

urlpatterns = [
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("security/me/", MeView.as_view(), name="security-me"),
    path("security/me/<int:user_id>/",
         MeByIdView.as_view(), name="security-me-by-id"),
    path("security/whoami/", whoami, name="security-whoami"),
    path("auth/sign-in", SignInView.as_view(), name="auth-sign-in"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
]
