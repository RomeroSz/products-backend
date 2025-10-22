# products-backend/catalog/api/views/public.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

# Servicio SQL
from catalog.api.services.catalog_service import get_catalog_items


def _parse_bool(val, default=None):
    if val is None:
        return default
    s = str(val).strip().lower()
    if s in ("1", "true", "t", "yes", "y"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    return default


@extend_schema(
    tags=["Catalog"],
    operation_id="catalog_items_list",
    parameters=[
        OpenApiParameter("type", str, required=False,
                         description="Filtra por tipo (p.ej. MONEDA, TIPO_ESTUDIO_RA)"),
        OpenApiParameter("parent_id", str, required=False,
                         description="Filtra por padre UUID"),
        OpenApiParameter("enabled", bool, required=False,
                         description="Solo habilitados (default: true)"),
        OpenApiParameter("include_roots", bool, required=False,
                         description="Incluir raíces (default: false)"),
        OpenApiParameter("limit", int, required=False,
                         description="Límite (default: 200)"),
        OpenApiParameter("offset", int, required=False,
                         description="Offset (default: 0)"),
    ],
    responses={200: OpenApiResponse(description="Lista de items de catálogo")}
)
class CatalogItemsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog_type = request.GET.get("type")
        parent_id = request.GET.get("parent_id")

        # Defaults que pediste:
        # - enabled: True si no viene
        # - include_roots: False si no viene (o sea, solo hojas / nodos con padre)
        enabled = _parse_bool(request.GET.get("enabled"), default=True)
        include_roots = _parse_bool(
            request.GET.get("include_roots"), default=False)

        try:
            limit = int(request.GET.get("limit", 200))
            offset = int(request.GET.get("offset", 0))
        except Exception:
            return Response({"code": "400.PARAMS_INVALID", "detail": "limit/offset deben ser enteros."}, status=400)

        items = get_catalog_items(
            item_type=catalog_type,
            parent_id=parent_id,
            enabled=enabled,
            include_roots=include_roots,
            limit=limit,
            offset=offset
        )
        # items ya viene en forma de dicts
        return Response({"items": items})
