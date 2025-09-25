from django.urls import path

from .views.me import MeView

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
]
