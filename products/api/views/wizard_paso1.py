# products/api/views/wizard_paso1.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.db import connection, transaction
import re


def normalize_poliza(s: str) -> str:
    """
    Normaliza el nombre técnico de póliza/contrato a MAYÚSCULAS con guiones bajos,
    alfanumérico y longitud máxima 64.
    """
    s = (s or "").strip().upper()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^A-Z0-9_]", "", s)
    return s[:64]


def validate_ramo_path(path_ids, modalidades):
    """
    Valida un path de ramos N1→N5 reutilizando las columnas reales de BD
    con alias hacia el contrato JSON expuesto por la API.
    - Requiere al menos N3 (Ramo Actuarial)
    - Para ciertas ramas exige llegar a N5
    - Verifica consistencia padre→hijo
    - Exige modalidades cuando el leaf es multiselección
    """
    if not isinstance(path_ids, list) or not path_ids:
        return False, "path_ids requerido"

    # Cargar ítems con columnas reales + alias al contrato de respuesta
    items = []
    with connection.cursor() as cur:
        for pid in path_ids:
            cur.execute(
                """
                SELECT id, item_type AS type, code, name, is_active AS enabled,
                       parent_id, depth AS level, attrs AS meta
                FROM catalog.item
                WHERE id = %s
                """,
                [pid],
            )
            row = cur.fetchone()
            if not row:
                return False, f"id inválido: {pid}"
            items.append(
                {
                    "id": row[0],
                    "type": row[1],
                    "code": row[2],
                    "name": row[3],
                    "enabled": row[4],
                    "parent_id": row[5],
                    "level": row[6],
                    "meta": row[7],
                }
            )

    # Regla: mínimo hasta N3
    last_level = items[-1].get("level") or 0
    if last_level < 3:
        return False, "Debes llegar al menos al Nivel 3 (Ramo Actuarial)."

    def requires_level5(path_items):
        """Determina si el path requiere llegar a N5 por códigos/meta."""
        codes = [it.get("code") for it in path_items if it]
        metas = [it.get("meta") or {} for it in path_items if it]
        needs = any(c in ("TRANS", "RTECN", "COMB", "AUTO_CAS", "RC_VEH")
                    for c in codes)
        if any(m.get("cg") is True for m in metas):
            needs = True
        return needs

    if requires_level5(items) and last_level < 5:
        return False, "Esta rama exige llegar a Nivel 5 (subcategoría y/o modalidad)."

    # Consistencia padre→hijo
    for i in range(1, len(items)):
        if items[i]["parent_id"] != items[i - 1]["id"]:
            return False, "El path no respeta la jerarquía padre→hijo."

    # Modalidades cuando el leaf lo requiera
    def is_multi(meta, code, name):
        if (meta or {}).get("multi") is True:
            return True
        if name and "*" in name:
            return True
        patterns = ("AP_IND", "AP_COL", "AP_OCV", "RC_VEH", "AUTO_CAS")
        return any(code and p in code for p in patterns)

    leaf = items[-1]
    if is_multi(leaf.get("meta"), leaf.get("code"), leaf.get("name")):
        if not modalidades or not isinstance(modalidades, list):
            return False, "Selecciona al menos una modalidad (IND/COL/...)."

    return True, None


@extend_schema(
    tags=["Products · Wizard"],
    operation_id="products_wizard_paso1_create",
    request={
        "type": "object",
        "properties": {
            "company_id": {"type": "string"},
            "nombre_comercial": {"type": "string"},
            "nombre_poliza": {"type": "string"},
            "is_combinado": {"type": "boolean"},
            "ramos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path_ids": {"type": "array", "items": {"type": "string"}},
                        "modalidades": {"type": "array", "items": {"type": "string"}, "nullable": True},
                    },
                    "required": ["path_ids"],
                },
            },
        },
        "required": ["company_id", "nombre_poliza", "nombre_comercial", "ramos"],
    },
    responses={200: OpenApiResponse(description="Borrador creado")},
)
class WizardCreateDraftView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        company_id = request.data.get("company_id")
        nombre_comercial = (request.data.get("nombre_comercial") or "").strip()
        nombre_poliza = normalize_poliza(
            request.data.get("nombre_poliza") or "")
        is_combinado = bool(request.data.get("is_combinado"))
        ramos = request.data.get("ramos") or []

        if not company_id or not nombre_comercial or not nombre_poliza:
            return Response(
                {"detail": "company_id, nombre_comercial y nombre_poliza son requeridos."},
                status=400,
            )
        if not ramos or not isinstance(ramos, list):
            return Response({"detail": "ramos es requerido (lista)."}, status=400)
        if not re.match(r"^[A-Z0-9_]+$", nombre_poliza):
            return Response({"detail": "nombre_poliza inválido (solo A-Z, 0-9, _)."}, status=400)

        # Validar cada selección de ramo
        for i, r in enumerate(ramos):
            ok, err = validate_ramo_path(
                r.get("path_ids") or [], r.get("modalidades") or [])
            if not ok:
                return Response({"detail": f"Ramo #{i + 1} inválido: {err}"}, status=400)

        # TODO: Inserciones reales en tus tablas de dominio (producto_draft, version_draft, etc.)
        # Por ahora devolvemos UUIDs simulados para encadenar con los siguientes pasos del flujo.
        with connection.cursor() as cur:
            cur.execute("SELECT gen_random_uuid()")  # requiere pgcrypto
            product_id = cur.fetchone()[0]
            cur.execute("SELECT gen_random_uuid()")
            version_id = cur.fetchone()[0]
            cur.execute("SELECT gen_random_uuid()")
            case_id = cur.fetchone()[0]
            cur.execute("SELECT gen_random_uuid()")
            product_case_id = cur.fetchone()[0]

        return Response(
            {
                "product_id": str(product_id),
                "version_id": str(version_id),
                "case_id": str(case_id),
                "product_case_id": str(product_case_id),
                "is_combinado": is_combinado,
            },
            status=200,
        )
