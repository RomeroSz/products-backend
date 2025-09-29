from django.contrib.auth.models import User
from django.db import connection
from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

try:
    from drf_spectacular.utils import (OpenApiParameter, OpenApiResponse,
                                       OpenApiTypes, extend_schema)
except Exception:  # pragma: no cover

    def extend_schema(*args, **kwargs):
        def _noop(f):
            return f

        return _noop

    OpenApiParameter = OpenApiTypes = OpenApiResponse = object  # fallback


class IsStaffOrSelfOrSuperuser(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        # Permitir self si la ruta trae user_id
        try:
            target_id = int(view.kwargs.get("user_id"))
        except Exception:
            return False
        return target_id == request.user.id


class MeByIdView(APIView):
    permission_classes = [IsAuthenticated, IsStaffOrSelfOrSuperuser]

    @extend_schema(
        tags=["Security"],
        operation_id="security_me_by_id",
        parameters=[
            OpenApiParameter(
                name="simulate_rls",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Si es true, hace set_context_from_user(user_id) temporalmente para devolver db_current_* del objetivo y luego restaura el contexto del solicitante.",
                required=False,
            )
        ],
        responses={
            200: OpenApiResponse(
                response={
                    "type": "object",
                    "properties": {
                        "target_user_id": {"type": "integer"},
                        "target_username": {"type": "string"},
                        "target_actor_id": {"type": "string", "nullable": True},
                        "target_company_id": {"type": "string", "nullable": True},
                        "db_current_actor_id": {"type": "string", "nullable": True},
                        "db_current_company_id": {"type": "string", "nullable": True},
                        "mode": {
                            "type": "string",
                            "enum": ["readonly", "simulate_rls"],
                        },
                    },
                },
                description="Identidad de un usuario por ID; opcionalmente simula su contexto RLS.",
            )
        },
    )
    def get(self, request, user_id: int):
        # 1) Resolver el usuario objetivo
        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise NotFound("Usuario no encontrado")

        # 2) Leer actor/company del objetivo SIN tocar contexto DB
        target_actor = target_company = None
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT a.id::text, a.company_id::text
                FROM "security".user_link ul
                JOIN "security".actor a ON a.id = ul.actor_id
                WHERE ul.user_id = %s
                LIMIT 1
            """,
                [target.id],
            )
            row = cur.fetchone()
            if row:
                target_actor, target_company = row[0], row[1]

        # 3) ¿Simular contexto RLS del objetivo?
        simulate = str(request.query_params.get("simulate_rls", "")).lower() in (
            "1",
            "true",
            "t",
            "yes",
            "y",
        )
        db_actor = db_company = None

        if simulate:
            # Guardar el contexto del solicitante para restaurar al final
            with connection.cursor() as cur:
                # set -> objetivo
                cur.execute(
                    'SELECT "security".set_context_from_user"(%s)'.replace('"', ""),
                    [target.id],
                )
                # leer current settings
                cur.execute("SELECT current_setting('app.current_actor_id', true)")
                db_actor = (cur.fetchone() or [None])[0]
                cur.execute("SELECT current_setting('app.current_company_id', true)")
                db_company = (cur.fetchone() or [None])[0]
                # restaurar -> solicitante
                cur.execute(
                    'SELECT "security".set_context_from_user"(%s)'.replace('"', ""),
                    [request.user.id],
                )
            mode = "simulate_rls"
        else:
            # Solo devolvemos los ids leídos por JOIN (no mutamos contexto)
            db_actor, db_company = target_actor, target_company
            mode = "readonly"

        return Response(
            {
                "target_user_id": target.id,
                "target_username": target.username,
                "target_actor_id": target_actor,
                "target_company_id": target_company,
                "db_current_actor_id": db_actor,
                "db_current_company_id": db_company,
                "mode": mode,
            }
        )
