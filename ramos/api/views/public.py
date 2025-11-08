# products-backend/ramos/api/views/public.py
from typing import List, Optional, Any, Dict
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ramos.api.services.tree_service import get_roots, get_children, get_tree
from ramos.api.services.validation_service import validate_path_and_modalidades
from ramos.api.services.modalidad_service import list_modalidades_for_node
from ramos.api.services.contable_service import resolve_contables_for_node
from ramos.api.services.ramos_flags_service import is_vida_by_path
from ramos.api.services.selection_service import resolve_selection
from ramos.api.services.docs_service import list_uniform_docs_for_node


def _company_id_from_request(request) -> Optional[str]:
    """
    Extrae company_id (SR) del usuario autenticado.
    Si no viene en el user, acepta cabecera 'X-Company-Id' como fallback (útil para pruebas).
    """
    cid = getattr(request.user, "company_id", None)
    if cid:
        return str(cid)
    hdr = request.headers.get("X-Company-Id")
    return hdr or None


PATH_IDS_SCHEMA = {
    "type": "object",
    "properties": {
        "pathIds": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "modalidades": {"type": "array", "items": {"type": "string"}, "nullable": True},
    },
    "required": ["pathIds"],
}

@extend_schema(tags=["Ramos · Público"], operation_id="ramos_roots",
    parameters=[OpenApiParameter("presented", bool, required=False,
                description="Usar raíces presentadas en orden GEN_OBL, GEN_PATR, GEN_PNV, VID (default true).")],
    responses={200: OpenApiResponse(description="Raíces de la taxonomía (N1)")}
)
class RamosRootsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        presented = (str(request.GET.get("presented") or "true").lower() != "false")
        items = get_roots(presented=presented)
        return Response({"items": items})


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_children",
    parameters=[OpenApiParameter("parentId", str, required=True)],
    responses={200: OpenApiResponse(description="Hijos directos del nodo (N+1)")}
)
class RamosChildrenView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        parent_id = request.GET.get("parentId")
        if not parent_id:
            return Response({"code":"400.MISSING_PARENT","detail":"parentId requerido."}, status=400)
        try:
            items = get_children(parent_id)
        except ValueError as e:
            return Response({"code":"400.PARENT_INVALID","detail":str(e)}, status=400)
        return Response({"items": items})


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_tree",
    parameters=[
        OpenApiParameter("depth", int, required=False, description="Profundidad máxima (default 4)."),
        OpenApiParameter("limit", int, required=False, description="(Ignorado si presented=true)."),
        OpenApiParameter("presented", bool, required=False, description="Usar raíces presentadas (default true)."),
    ],
    responses={200: OpenApiResponse(description="Árbol ligero hasta depth")}
)
class RamosTreeView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        try:
            depth = int(request.GET.get("depth") or 4)
            limit = int(request.GET.get("limit") or 50)
            presented = (str(request.GET.get("presented") or "true").lower() != "false")
        except Exception:
            return Response({"code":"400.PARAMS_INVALID","detail":"depth/limit deben ser enteros."}, status=400)
        if depth < 1 or depth > 6:
            return Response({"code":"400.DEPTH_RANGE","detail":"depth debe estar entre 1 y 6."}, status=400)

        company_id = _company_id_from_request(request)
        data = get_tree(depth=depth, limit=limit, company_id=company_id, presented=presented)
        return Response({"roots": data})


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_validate_path",
    request=PATH_IDS_SCHEMA,
    responses={200: OpenApiResponse(description="Validación de trayectoria y modalidades"),
               400: OpenApiResponse(description="Errores de validación")}
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
            return Response({"code":"400.VALIDATION","detail":str(e)}, status=400)
        return Response(result)


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_modalidades",
    responses={200: OpenApiResponse(description="Listado IND/COL por nodo")}
)
class RamosModalidadesView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, node_id: str):
        try:
            payload = list_modalidades_for_node(node_id)
        except ValueError as e:
            return Response({"code":"404.RAMO_NOT_FOUND","detail":str(e)}, status=404)
        return Response(payload)


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_contables",
    responses={200: OpenApiResponse(description="Contables aplicables por herencia")}
)
class RamosContablesView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, node_id: str):
        try:
            payload = resolve_contables_for_node(node_id)
        except ValueError as e:
            return Response({"code":"404.RAMO_NOT_FOUND","detail":str(e)}, status=404)
        return Response(payload)


@extend_schema(tags=["Ramos · Público"], operation_id="ramos_is_vida",
    request={"application/json": {"oneOf":[
        {"type":"object","properties":{"pathIds":{"type":"array","items":{"type":"string"}}},"required":["pathIds"]},
        {"type":"object","properties":{"paths":{"type":"array","items":{"type":"array","items":{"type":"string"}}}},"required":["paths"]},
    ]}},
    responses={200: OpenApiResponse(description="Marca si el path pertenece a Vida")}
)
class IsVidaPathView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        body = request.data or {}
        if "pathIds" in body:
            paths = [body.get("pathIds") or []]
        else:
            paths = body.get("paths") or []
        if not isinstance(paths, list) or not all(isinstance(p, list) for p in paths):
            return Response({"detail":"paths / pathIds inválido"}, status=400)

        out = []
        for p in paths:
            try:
                ok, ramo = is_vida_by_path(p)
                out.append({"pathIds": p, "is_vida": ok,
                            "ramo": ramo and {"id":ramo["id"],"code":ramo["code"],"name":ramo["name"]} or None})
            except ValueError as e:
                out.append({"pathIds": p, "is_vida": False, "error": str(e)})
        return Response({"results": out})


# ============ NUCLEO NUEVO: selección consolidada ============
@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_selection_resolve",
    request={
        "application/json":{
            "type":"object",
            "properties":{
                "main":{"type":"array","items":{"type":"array","items":{"type":"string"}}},
                "annex":{"type":"array","items":{"type":"array","items":{"type":"string"}},"nullable":True}
            },
            "required":["main"]
        }
    },
    responses={200: OpenApiResponse(description="Consolidado: comisión, combinado, docs uniformes")}
)
class SelectionResolveView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        company_id = _company_id_from_request(request)
        payload = request.data or {}
        try:
            result = resolve_selection(payload, company_id=company_id)
        except ValueError as e:
            return Response({"code":"400.VALIDATION","detail":str(e)}, status=400)
        return Response(result)


@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_docs_uniformes",
    responses={200: OpenApiResponse(description="Documentos uniformes por nodo")}
)
class RamosDocsView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, node_id: str):
        try:
            docs = list_uniform_docs_for_node(node_id)
        except ValueError as e:
            return Response({"code":"404.RAMO_NOT_FOUND","detail":str(e)}, status=404)
        return Response(docs)
