from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # OpenAPI + Swagger
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    # Health & Metrics
    path("health/", include("health_check.urls")),
    path("", include("django_prometheus.urls")),
    # RQ Dashboard (opcional)
    path("rq/", include("django_rq.urls")),
    # JWT auth (cuando abras seguridad)
    path(
        "api/auth/", include("apps.core_auth.urls")
    ),  # si prefieres, puedes montarlo directo aquí
]
