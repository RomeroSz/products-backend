# catalog/api/views/catalog_items.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db import connection
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter


# Contrato JSON "amigable" (alias a columnas reales):
#  - item_type   -> type
#  - is_active   -> enabled
#  - depth       -> level
#  - attrs       -> meta

def row_to_item(r):
    return {
        "id": r[0],
        "type": r[1],
        "code": r[2],
        "name": r[3],
        "enabled": r[4],
        "parent_id": r[5],
        "level": r[6],
        "meta": r[7],
    }


@extend_schema(
    tags=["Catalog"],
    operation_id="catalog_items_list",
    parameters=[
        OpenApiParameter(
            "type",
            str,
            required=False,
            description="Filtra por tipo (RAMO_TAX, RAMO, MODALIDAD, MONEDA, etc.)",
        ),
        OpenApiParameter("parent_id", str, required=False,
                         description="Filtra por padre UUID"),
        OpenApiParameter("level", int, required=False,
                         description="Filtra por nivel jerárquico"),
        OpenApiParameter("enabled", bool, required=False,
                         description="Solo habilitados"),
        OpenApiParameter("limit", int, required=False),
        OpenApiParameter("offset", int, required=False),
    ],
    responses={200: OpenApiResponse(description="Lista de items de catálogo")},
)
class CatalogItemsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = """
        SELECT id, item_type AS type, code, name, is_active AS enabled,
               parent_id, depth AS level, attrs AS meta
        FROM catalog.item
        WHERE 1=1
        """
        params = []

        if (typ := request.GET.get("type")):
            q += " AND item_type=%s"
            params.append(typ)
        if (pid := request.GET.get("parent_id")):
            q += " AND parent_id=%s"
            params.append(pid)
        if (lvl := request.GET.get("level")):
            q += " AND depth=%s"
            try:
                params.append(int(lvl))
            except ValueError:
                return Response({"detail": "level debe ser entero"}, status=400)
        if (enabled := request.GET.get("enabled")):
            q += " AND is_active=%s"
            params.append(enabled.lower() in ("1", "true", "t", "yes", "y"))

        q += " ORDER BY COALESCE((attrs->>'ord')::int, 999), name"

        try:
            limit = int(request.GET.get("limit", 200))
            offset = int(request.GET.get("offset", 0))
        except ValueError:
            return Response({"detail": "limit/offset deben ser enteros"}, status=400)

        q += " LIMIT %s OFFSET %s"
        params += [limit, offset]

        with connection.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return Response([row_to_item(r) for r in rows])


@extend_schema(
    tags=["Catalog"],
    operation_id="catalog_items_by_id",
    responses={200: OpenApiResponse(description="Item de catálogo")},
)
class CatalogItemByIdView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, item_id):
        q = """
        SELECT id, item_type AS type, code, name, is_active AS enabled,
               parent_id, depth AS level, attrs AS meta
        FROM catalog.item
        WHERE id=%s
        """
        with connection.cursor() as cur:
            cur.execute(q, [item_id])
            row = cur.fetchone()
        if not row:
            return Response(status=404)
        return Response(row_to_item(row))


@extend_schema(
    tags=["Catalog"],
    operation_id="catalog_items_search",
    parameters=[
        OpenApiParameter("q", str, required=True,
                         description="Texto a buscar en code/name (ilike)"),
        OpenApiParameter("type", str, required=False),
        OpenApiParameter("limit", int, required=False),
        OpenApiParameter("offset", int, required=False),
    ],
    responses={200: OpenApiResponse(description="Resultados de búsqueda")},
)
class CatalogItemsSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        term = request.GET.get("q", "").strip()
        if not term:
            return Response({"detail": "q requerido"}, status=400)

        q = """
        SELECT id, item_type AS type, code, name, is_active AS enabled,
               parent_id, depth AS level, attrs AS meta
        FROM catalog.item
        WHERE (code ILIKE %s OR name ILIKE %s)
        """
        params = [f"%{term}%", f"%{term}%"]

        if (typ := request.GET.get("type")):
            q += " AND item_type=%s"
            params.append(typ)

        q += " ORDER BY COALESCE((attrs->>'ord')::int, 999), name"

        try:
            limit = int(request.GET.get("limit", 100))
            offset = int(request.GET.get("offset", 0))
        except ValueError:
            return Response({"detail": "limit/offset deben ser enteros"}, status=400)

        q += " LIMIT %s OFFSET %s"
        params += [limit, offset]

        with connection.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return Response([row_to_item(r) for r in rows])
