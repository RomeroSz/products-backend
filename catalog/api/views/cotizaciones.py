# catalog/api/views/cotizaciones.py
from typing import Any, Dict, Optional
from uuid import uuid4

from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

import re
import json


UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def is_uuid(s: Optional[str]) -> bool:
    return bool(s) and bool(UUID_RX.match(str(s)))


def row_to_item(r) -> Dict[str, Any]:
    # id, item_type, code, name, is_active
    return {"id": str(r[0]), "type": r[1], "code": r[2], "name": r[3], "is_active": bool(r[4])}


def fetch_ramo(ramo_id: str) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, item_type, code, name, is_active
            FROM catalog.item
            WHERE id=%s
            """,
            [ramo_id],
        )
        row = cur.fetchone()
    return row_to_item(row) if row else None


def ramo_requires_modalities(ramo_id: str) -> bool:
    """
    True si existen modalidades habilitadas para este ramo en la pivote core.ramo_modalidad.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(1)
            FROM core.ramo_modalidad rm
            JOIN catalog.item m ON m.id = rm.modalidad_id
            WHERE rm.ramo_id = %s
              AND rm.is_enabled = true
              AND m.item_type = 'MODALIDAD'
              AND m.is_active = true
            """,
            [ramo_id],
        )
        n = cur.fetchone()[0]
    return int(n or 0) > 0


def is_modality_allowed_for_ramo(ramo_id: str, modalidad_id: str) -> bool:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM core.ramo_modalidad rm
            JOIN catalog.item m ON m.id = rm.modalidad_id
            WHERE rm.ramo_id = %s
              AND rm.modalidad_id = %s
              AND rm.is_enabled = true
              AND m.item_type = 'MODALIDAD'
              AND m.is_active = true
            LIMIT 1
            """,
            [ramo_id, modalidad_id],
        )
        row = cur.fetchone()
    return bool(row)


def fetch_modalidad(modalidad_id: str) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, item_type, code, name, is_active
            FROM catalog.item
            WHERE id=%s AND item_type='MODALIDAD'
            """,
            [modalidad_id],
        )
        row = cur.fetchone()
    return row_to_item(row) if row else None


@extend_schema(
    tags=["Quotes · Cotizaciones"],
    operation_id="cotizaciones_create",
    request={
        "type": "object",
        "properties": {
            "ramoId": {"type": "string"},
            "modalidadId": {"type": "string", "nullable": True},
            "tomador": {"type": "object"},
            "asegurados": {"type": "array", "items": {"type": "object"}},
            "metadata": {"type": "object"},
        },
        "required": ["ramoId"],
    },
    responses={
        201: OpenApiResponse(description="Cotización creada"),
        400: OpenApiResponse(description="Error de validación"),
        404: OpenApiResponse(description="RAMO_NOT_FOUND"),
    },
)
class CotizacionesCreateView(APIView):
    """
    Crea una cotización a partir de (ramoId, modalidadId?).
    Reglas:
      - ramoId requerido, debe ser catalog.item (type='RAMO', is_active=true)
      - Si el ramo tiene modalidades habilitadas en core.ramo_modalidad:
          * modalidadId es obligatoria y debe pertenecer al set permitido
      - Si el ramo NO tiene modalidades habilitadas:
          * modalidadId NO debe enviarse
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        body = request.data or {}
        ramo_id = body.get("ramoId")
        modalidad_id = body.get("modalidadId")
        tomador = body.get("tomador") or {}
        asegurados = body.get("asegurados") or []
        metadata = body.get("metadata") or {}

        # ---- Validaciones de entrada
        if not ramo_id:
            return Response(
                {"code": "400.RAMO_REQUIRED", "detail": "ramoId es requerido."},
                status=400,
            )
        if not is_uuid(ramo_id):
            return Response(
                {"code": "400.RAMO_INVALID", "detail": "ramoId debe ser UUID."},
                status=400,
            )

        ramo = fetch_ramo(ramo_id)
        if not ramo or ramo["type"] != "RAMO" or ramo["is_active"] is not True:
            return Response(
                {"code": "404.RAMO_NOT_FOUND",
                    "detail": "Ramo inexistente o inactivo."},
                status=404,
            )

        requires_mod = ramo_requires_modalities(ramo_id)

        if requires_mod:
            # Debe venir modalidadId
            if not modalidad_id:
                return Response(
                    {"code": "400.MODALITY_REQUIRED",
                     "detail": "Este ramo exige modalidad; envía modalidadId válido (IND/COL/...)."},
                    status=400,
                )
            if not is_uuid(modalidad_id):
                return Response(
                    {"code": "400.MODALITY_INVALID",
                        "detail": "modalidadId debe ser UUID."},
                    status=400,
                )
            # Debe estar habilitada para el ramo
            if not is_modality_allowed_for_ramo(ramo_id, modalidad_id):
                return Response(
                    {"code": "400.MODALITY_NOT_ALLOWED",
                        "detail": "La modalidad no está habilitada para este ramo."},
                    status=400,
                )
            modalidad = fetch_modalidad(modalidad_id)
            if not modalidad or modalidad["is_active"] is not True:
                return Response(
                    {"code": "400.MODALITY_NOT_ALLOWED",
                     "detail": "La modalidad no está habilitada o no existe."},
                    status=400,
                )
        else:
            # No debe venir modalidadId
            if modalidad_id:
                return Response(
                    {"code": "400.MODALITY_NOT_APPLICABLE",
                     "detail": "Este ramo no admite modalidad. No envíes modalidadId."},
                    status=400,
                )
            modalidad = None

        # ---- Validaciones de negocio adicionales (sumas, límites, etc.)
        # TODO: Aplica tus reglas propias aquí. Si algo falla, devuelve 400 con code específico.

        # ---- Persistencia:
        # Si aún no tienes tabla de cotizaciones, dejamos un mock de respuesta 201 con IDs.
        # Si ya tienes tabla (ej. core.cotizacion), inserta y retorna su ID.
        quote_id = str(uuid4())

        # ---- Resumen normalizado (útil para front/confirmaciones)
        payload_resumen = {
            "quoteId": quote_id,
            "ramo": {
                "id": ramo["id"],
                "code": ramo["code"],
                "name": ramo["name"],
            },
            "modalidad": (
                {
                    "id": modalidad["id"],
                    "code": modalidad["code"],
                    "name": modalidad["name"],
                } if modalidad else None
            ),
            "tomador": tomador,
            "asegurados": asegurados,
            "metadata": metadata,
            # campos calculados (prima/resumen) se pueden agregar luego
        }

        return Response(payload_resumen, status=201)
