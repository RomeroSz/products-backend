# security/api/views/me.py
from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

try:
    # Si usas drf-spectacular
    from drf_spectacular.utils import OpenApiResponse, extend_schema
except Exception:  # pragma: no cover

    def extend_schema(*args, **kwargs):
        def _noop(f):
            return f

        return _noop

    OpenApiResponse = dict  # fallback


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Security"],
        operation_id="security_me",
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "integer"},
                        "username": {"type": "string"},
                        "is_staff": {"type": "boolean"},
                        "is_superuser": {"type": "boolean"},
                        "request_actor_id": {"type": "string", "nullable": True},
                        "request_company_id": {"type": "string", "nullable": True},
                        "db_current_actor_id": {"type": "string", "nullable": True},
                        "db_current_company_id": {"type": "string", "nullable": True},
                    },
                },
                description="Identidad efectiva de la request y contexto DB (RLS).",
            )
        },
    )
    def get(self, request):
        # Valores por request (middleware)
        req_actor = getattr(request, "actor_id", None)
        req_company = getattr(request, "company_id", None)

        # Valores en la sesión DB (RLS)
        db_actor = db_company = None
        with connection.cursor() as cur:
            cur.execute("SELECT current_setting('app.current_actor_id', true)")
            row = cur.fetchone()
            db_actor = row[0] if row else None

            cur.execute("SELECT current_setting('app.current_company_id', true)")
            row = cur.fetchone()
            db_company = row[0] if row else None

        return Response(
            {
                "user_id": request.user.id,
                "username": request.user.username,
                "is_staff": request.user.is_staff,
                "is_superuser": request.user.is_superuser,
                "request_actor_id": req_actor,
                "request_company_id": req_company,
                "db_current_actor_id": db_actor,
                "db_current_company_id": db_company,
            }
        )
