# products-backend/ramos/api/views/selection.py
from typing import Optional
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from ramos.api.services.selection_service import resolve_selection

def _company_id_from_request(request) -> Optional[str]:
    cid = getattr(request.user, "company_id", None)
    if cid:
        return str(cid)
    hdr = request.headers.get("X-Company-Id")
    return hdr or None

@extend_schema(
    tags=["Ramos · Público"],
    operation_id="ramos_selection_preview",
    request={
        "application/json": {
            "type":"object",
            "properties":{
                "main":{"type":"array","items":{"type":"array","items":{"type":"string"}}},
                "annex":{"type":"array","items":{"type":"array","items":{"type":"string"}},"nullable":True}
            },
            "required":["main"]
        }
    },
    responses={200: OpenApiResponse(description="Preview: comisión, combinado, docs")}
)
class SelectionPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company_id = _company_id_from_request(request)
        payload = request.data or {}
        try:
            result = resolve_selection(payload, company_id=company_id)
        except ValueError as e:
            return Response({"code":"400.VALIDATION","detail":str(e)}, status=400)
        return Response(result)
