from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.application.db import set_db_context_from_request
from products.application.selectors.wizard_status import get_wizard_status


class WizardStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, case_id: str):
        set_db_context_from_request(request)
        version_id = request.query_params.get("version_id")
        if not version_id:
            return Response({"detail": "version_id es requerido"}, status=400)
        s = get_wizard_status(version_id)
        return Response(
            {
                "product_id": s.product_id,
                "version_id": s.version_id,
                "product_case_id": s.product_case_id,
                "counts": {
                    "cg": s.cg_count,
                    "cp": s.cp_count,
                    "annex": s.annex_count,
                    "format": s.format_count,
                    "ra": s.ra_count,
                },
                "estado": s.estado,
                "is_locked": s.is_locked,
                "can_validate": s.can_validate,
                "checklist": {
                    "docs_minimos": (s.cg_count > 0 and s.cp_count > 0),
                    "ra_configurado": (s.ra_count > 0),
                },
            }
        )
