# products-backend/ramos/api/views/public.py
from typing import List, Optional
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ramos.api.services.tree_service import get_roots, get_children, get_tree
from ramos.api.services.validation_service import validate_path_and_modalidades
from ramos.api.services.modalidad_service import list_modalidades_for_node
from ramos.api.services.contable_service import resolve_contables_for_node


# ------------------------------
# Helpers de documentación
# ------------------------------

PATH_IDS_SCHEMA = {
    "type": "object",
    "properties": {
        "pathIds": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "modalidades": {"type": "array", "items": {"type": "string"}, "nullable": True},
    },
    "required": ["pathIds"],
}


# ------------------------------
# Public Views
# ------------------------------

@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_roots",
    responses={200: OpenApiResponse(description="Raíces de la taxonomía (N1)")},
)
class RamosRootsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = get_roots()
        return Response({"items": items})


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_children",
    parameters=[OpenApiParameter("parentId", str, required=True)],
    responses={200: OpenApiResponse(description="Hijos directos del nodo (N+1)")},
)
class RamosChildrenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        parent_id = request.GET.get("parentId")
        if not parent_id:
            return Response({"code": "400.MISSING_PARENT", "detail": "parentId requerido."}, status=400)
        try:
            items = get_children(parent_id)
        except ValueError as e:
            return Response({"code": "400.PARENT_INVALID", "detail": str(e)}, status=400)
        return Response({"items": items})


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_tree",
    parameters=[
        OpenApiParameter("depth", int, required=False, description="Profundidad máxima (default 3)."),
        OpenApiParameter("limit", int, required=False, description="Máximo de raíces a retornar (default 50)."),
    ],
    responses={200: OpenApiResponse(description="Árbol ligero hasta depth")},
)
class RamosTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            depth = int(request.GET.get("depth") or 3)
            limit = int(request.GET.get("limit") or 50)
        except Exception:
            return Response({"code": "400.PARAMS_INVALID", "detail": "depth/limit deben ser enteros."}, status=400)

        if depth < 1 or depth > 5:
            return Response({"code": "400.DEPTH_RANGE", "detail": "depth debe estar entre 1 y 5."}, status=400)

        data = get_tree(depth=depth, limit=limit)
        return Response({"roots": data})


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_validate_path",
    request=PATH_IDS_SCHEMA,
    responses={
        200: OpenApiResponse(description="Validación de trayectoria y modalidades"),
        400: OpenApiResponse(description="Errores de validación"),
    },
)
class RamosValidatePathView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        body = request.data or {}
        path_ids: List[str] = body.get("pathIds") or []
        modalidades_in: Optional[List[str]] = body.get("modalidades")

        try:
            result = validate_path_and_modalidades(path_ids, modalidades_in)
        except ValueError as e:
            # ValueError → errores de validación esperables
            return Response({"code": "400.VALIDATION", "detail": str(e)}, status=400)
        return Response(result)


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_modalidades",
    responses={200: OpenApiResponse(description="Listado IND/COL por nodo")},
)
class RamosModalidadesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, node_id):
        try:
            payload = list_modalidades_for_node(node_id)  # acepta uuid.UUID o str
        except ValueError as e:
            return Response({"code": "404.RAMO_NOT_FOUND", "detail": str(e)}, status=404)
        return Response(payload)


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_contables",
    responses={200: OpenApiResponse(description="Contables aplicables por herencia")},
)
class RamosContablesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, node_id):
        try:
            payload = resolve_contables_for_node(node_id)  # acepta uuid.UUID o str
        except ValueError as e:
            # Node no existe / inválido
            return Response({"code": "404.RAMO_NOT_FOUND", "detail": str(e)}, status=404)
        return Response(payload)
