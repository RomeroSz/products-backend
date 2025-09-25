from django.urls import include, path
from rest_framework.routers import DefaultRouter

# Router vacÃ­o por ahora (evita 404 en include)
router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
]
