# scaffold.ps1
$ErrorActionPreference = "Stop"

$apps = @(
 "common","security","catalog","products","expediente","workflow",
 "incentives","advertising","accounting","stg","audit","reporting","notifications"
)

# carpetas por app
foreach ($app in $apps) {
  New-Item -ItemType Directory -Force -Path "$app/domain","$app/application","$app/infrastructure","$app/api","$app/tests" | Out-Null
  New-Item -ItemType Directory -Force -Path "$app/application/use_cases","$app/application/selectors","$app/api/serializers","$app/api/views" | Out-Null
  @"
# $app domain entities (stub)
"@ | Set-Content "$app/domain/entities.py" -Encoding UTF8
  @"
# $app domain rules (stub)
"@ | Set-Content "$app/domain/rules.py" -Encoding UTF8
  @"
# $app domain services (stub)
"@ | Set-Content "$app/domain/services.py" -Encoding UTF8
  @"
# $app domain events (stub)
"@ | Set-Content "$app/domain/events.py" -Encoding UTF8
  @"
# $app domain errors (stub)
"@ | Set-Content "$app/domain/errors.py" -Encoding UTF8
  @"
# $app application DTOs (stub)
"@ | Set-Content "$app/application/dto.py" -Encoding UTF8
  @"
# $app application policies/permissions (stub)
"@ | Set-Content "$app/application/policies.py" -Encoding UTF8
  @"
# $app infra models (stub ORM)
from django.db import models
"@ | Set-Content "$app/infrastructure/models.py" -Encoding UTF8
  @"
# $app infra repositories/selectors (stub)
"@ | Set-Content "$app/infrastructure/repositories.py" -Encoding UTF8
  @"
# $app infra mappers (stub)
"@ | Set-Content "$app/infrastructure/mappers.py" -Encoding UTF8
  @"
# $app infra outbox (stub)
"@ | Set-Content "$app/infrastructure/outbox.py" -Encoding UTF8
  @"
# $app infra tasks (stub)
"@ | Set-Content "$app/infrastructure/tasks.py" -Encoding UTF8
  @"
# $app api serializers (stub)
"@ | Set-Content "$app/api/serializers/__init__.py" -Encoding UTF8
  @"
# $app api views (stub)
"@ | Set-Content "$app/api/views/__init__.py" -Encoding UTF8
  @"
from django.urls import include, path
from rest_framework.routers import DefaultRouter

# Router vacío por ahora (evita 404 en include)
router = DefaultRouter()

urlpatterns = [
    path("", include(router.urls)),
]
"@ | Set-Content "$app/api/routers.py" -Encoding UTF8
  @"
# $app api errors (stub)
"@ | Set-Content "$app/api/errors.py" -Encoding UTF8
  @"
# $app tests package
"@ | Set-Content "$app/tests/__init__.py" -Encoding UTF8
}

# COMMON utilidades
New-Item -ItemType Directory -Force -Path "common/api","common/db","common/middleware" | Out-Null
@"
from rest_framework.pagination import LimitOffsetPagination

class DefaultPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200
"@ | Set-Content "common/api/pagination.py" -Encoding UTF8

@"
# Exceptions mapping (stub)
"@ | Set-Content "common/api/exceptions.py" -Encoding UTF8

@"
# OpenAPI helpers (stub)
"@ | Set-Content "common/api/schema.py" -Encoding UTF8

@"
# DB routers/signals (stub)
"@ | Set-Content "common/db/routers.py" -Encoding UTF8
@"
# Signals (stub)
"@ | Set-Content "common/db/signals.py" -Encoding UTF8

@"
from django.utils.deprecation import MiddlewareMixin

class ActorContextMiddleware(MiddlewareMixin):
    \"\"\"Resuelve actor_id/company_id desde security.user_link y los inyecta al request.
    * No contiene reglas de negocio (solo contexto).
    * En infra postgres puedes aplicar RLS via SET LOCAL si corresponde.
    \"\"\"
    def process_request(self, request):
        request.actor_id = None
        request.company_id = None
        # TODO: resolver desde security (cuando implementes user_link)
        return None
"@ | Set-Content "common/middleware/actor_context.py" -Encoding UTF8
"Scaffold listo."
