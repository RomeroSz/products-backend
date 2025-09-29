# common/middleware/actor_context.py
from django.conf import settings
from django.db import connection
from django.utils.deprecation import MiddlewareMixin


class ActorContextMiddleware(MiddlewareMixin):
    header_actor = "HTTP_X_ACTOR_ID"
    header_company = "HTTP_X_COMPANY_ID"

    def process_request(self, request):
        request.actor_id = None
        request.company_id = None

        # 0) Headers de prueba solo en DEBUG
        if getattr(settings, "DEBUG", False):
            aid = request.META.get(self.header_actor)
            cid = request.META.get(self.header_company)
            if aid:
                request.actor_id = aid
            if cid:
                request.company_id = cid

        # 1) Si el usuario está autenticado: setear contexto RLS y resolver actor/company
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return None

        with connection.cursor() as cur:
            # Cargar contexto de sesión para RLS/funciones
            cur.execute('SELECT "security".set_context_from_user(%s)', [user.id])

            # Resolver actor y compañía en un solo roundtrip
            cur.execute(
                """
                SELECT a.id::text, a.company_id::text
                FROM "security".user_link ul
                JOIN "security".actor a ON a.id = ul.actor_id
                WHERE ul.user_id = %s
                LIMIT 1
            """,
                [user.id],
            )
            row = cur.fetchone()

        if row:
            request.actor_id, request.company_id = row[0], row[1]

        return None
