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
    path("api/v1/security/", include("security.api.routers")),
    path("api/v1/catalog/", include("catalog.api.routers")),
    path("api/v1/products/", include("products.api.routers")),
    path("api/v1/expedientes/", include("expediente.api.routers")),
    path("api/v1/workflow/", include("workflow.api.routers")),
    path("api/v1/incentives/", include("incentives.api.routers")),
    path("api/v1/advertising/", include("advertising.api.routers")),
    path("api/v1/accounting/", include("accounting.api.routers")),
    path("api/v1/stg/", include("stg.api.routers")),
    path("api/v1/audit/", include("audit.api.routers")),
    path("api/v1/reporting/", include("reporting.api.routers")),
    path("api/v1/notifications/", include("notifications.api.routers")),
]
