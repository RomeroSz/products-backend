# security/api/routers.py
from django.urls import path

from .views.me import MeView
from .views.me_by_id import MeByIdView
from .views.whoami import whoami

urlpatterns = [
    path("me/", MeView.as_view(), name="security-me"),
    path("me/<int:user_id>/", MeByIdView.as_view(), name="security-me-by-id"),
    path("whoami/", whoami, name="security-whoami"),
]
