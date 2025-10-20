from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Observabilidad
    path("metrics/", include("django_prometheus.urls")),
    path("health/", include("health_check.urls")),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    # API v1 por dominio (routers vacíos por ahora: no 404)
    path("api/", include("security.api.routers")),
    path("api/", include("catalog.api.routers")),
    path("api/", include("ramos.api.routers")),
    path("api/", include("products.api.routers")),
    path("api/", include("expediente.api.routers")),
    path("api/", include("workflow.api.routers")),
    path("api/", include("incentives.api.routers")),
    path("api/", include("advertising.api.routers")),
    path("api/", include("accounting.api.routers")),
    path("api/", include("stg.api.routers")),
    path("api/", include("audit.api.routers")),
    path("api/", include("reporting.api.routers")),
    path("api/", include("notifications.api.routers")),
]
