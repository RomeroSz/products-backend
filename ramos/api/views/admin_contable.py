# products-backend/ramos/api/views/admin_contable.py
from typing import Any, Dict, List
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter

from ramos.api.services.contable_service import (
    list_mappings_for_node,
    create_mapping,
    delete_mapping,
    bulk_upsert_mappings,
    bulk_insert_mappings,
    bulk_replace_mappings,
    audit_unmapped_by_scope,
)


# ------------------------------
# Admin · Contable
# ------------------------------

@extend_schema(
    tags=["Admin · Contable"],
    operation_id="admin_contable_mapping_list",
    parameters=[
        OpenApiParameter("nodeCode", str, required=False,
                         description="Código del nodo (alternativo a nodeId)"),
        OpenApiParameter("nodeId", str, required=False,
                         description="UUID del nodo (alternativo a nodeCode)"),
    ],
    responses={200: OpenApiResponse(
        description="Lista vínculos contables (directos) para un nodo")},
)
class AdminContableMappingListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        node_code = request.GET.get("nodeCode")
        node_id = request.GET.get("nodeId")
        if not node_code and not node_id:
            return Response({"code": "400.MISSING_PARAM", "detail": "Debe enviar nodeCode o nodeId."}, status=400)
        try:
            items = list_mappings_for_node(
                node_code=node_code, node_id=node_id)
        except ValueError as e:
            return Response({"code": "404.NODE_NOT_FOUND", "detail": str(e)}, status=404)
        return Response({"items": items})


@extend_schema(
    tags=["Admin · Contable"],
    operation_id="admin_contable_mapping_create",
    request={
        "type": "object",
        "properties": {"nodeId": {"type": "string"}, "contableCode": {"type": "string"}},
        "required": ["nodeId", "contableCode"],
    },
    responses={
        201: OpenApiResponse(description="Vínculo contable creado"),
        400: OpenApiResponse(description="Error de validación"),
        409: OpenApiResponse(description="Duplicado"),
    },
)
class AdminContableMappingCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        node_id = request.data.get("nodeId")
        cont_code = request.data.get("contableCode")
        if not node_id or not cont_code:
            return Response({"code": "400.MISSING_PARAM", "detail": "nodeId y contableCode son requeridos."}, status=400)
        try:
            mapping = create_mapping(node_id=node_id, contable_code=cont_code)
        except ValueError as e:
            msg = str(e)
            if msg.startswith("409."):
                return Response({"code": "409.MAPPING_DUPLICATE", "detail": msg}, status=409)
            return Response({"code": "400.VALIDATION", "detail": msg}, status=400)
        return Response(mapping, status=201)


@extend_schema(
    tags=["Admin · Contable"],
    operation_id="admin_contable_mapping_delete",
    responses={
        200: OpenApiResponse(description="Vínculo contable eliminado"),
        404: OpenApiResponse(description="RTC no encontrado"),
    },
)
class AdminContableMappingDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, rtc_id: str):
        try:
            delete_mapping(rtc_id)
        except ValueError as e:
            return Response({"code": "404.MAPPING_NOT_FOUND", "detail": str(e)}, status=404)
        return Response({"ok": True})


@extend_schema(
    tags=["Admin · Contable"],
    operation_id="admin_contable_mapping_bulk",
    request={
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"nodeCode": {"type": "string"}, "contCode": {"type": "string"}},
                    "required": ["nodeCode", "contCode"],
                },
            },
            "mode": {"type": "string", "enum": ["insert", "upsert", "replace"]},
        },
        "required": ["rows", "mode"],
    },
    responses={200: OpenApiResponse(description="Carga masiva procesada")},
)
class AdminContableMappingBulkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        rows: List[Dict[str, str]] = request.data.get("rows") or []
        mode = (request.data.get("mode") or "upsert").lower()
        if mode not in ("insert", "upsert", "replace"):
            return Response({"code": "400.MODE_INVALID", "detail": "mode debe ser insert|upsert|replace."}, status=400)
        if not rows:
            return Response({"code": "400.EMPTY_ROWS", "detail": "rows no puede ser vacío."}, status=400)

        if mode == "insert":
            result = bulk_insert_mappings(rows)
        elif mode == "upsert":
            result = bulk_upsert_mappings(rows)
        else:
            result = bulk_replace_mappings(rows)
        return Response(result)


@extend_schema(
    tags=["Admin · Contable"],
    operation_id="admin_contable_audit_unmapped",
    parameters=[OpenApiParameter(
        "scope", str, required=False, description="leaf|ramo|category (default leaf)")],
    responses={200: OpenApiResponse(
        description="Listado de nodos sin contable (considerando herencia)")},
)
class AdminContableAuditUnmappedView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scope = (request.GET.get("scope") or "leaf").lower()
        if scope not in ("leaf", "ramo", "category"):
            return Response({"code": "400.SCOPE_INVALID", "detail": "scope debe ser leaf|ramo|category."}, status=400)
        items = audit_unmapped_by_scope(scope)
        return Response({"items": items, "total": len(items)})
