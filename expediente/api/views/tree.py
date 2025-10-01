from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.application.db import set_db_context_from_request


class CaseTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, product_case_id: str):
        set_db_context_from_request(request)

        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT p.id AS product_id, vp.id AS version_id, p.nombre, vp.estado, vp.version
                FROM core.product_case pc
                JOIN core.product p ON p.id = pc.product_id
                LEFT JOIN core.version_product vp ON vp.idproduct = p.id
                WHERE pc.id=%s
                ORDER BY vp.created_at DESC
                LIMIT 1
            """,
                [product_case_id],
            )
            header = cur.fetchone()
            if not header:
                return Response({"detail": "expediente no encontrado"}, status=404)
            product_id, version_id, nombre, estado, nro_version = header

            def fetch_docs(sql: str, params):
                cur.execute(sql, params)
                cols = [c[0] for c in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]

            cg = fetch_docs(
                """
                SELECT l.id link_id, c.id cg_id, d.id doc_id, c.logical_code, c.version, l.estado, l.vigencia,
                       d.nombre, d.mime, d.archivo_url, d.tamano, d.referencia_normativa
                FROM link.vp_to_cg l
                JOIN core.cg c ON c.id = l.idcg
                JOIN core.documento d ON d.id = c.documento_id
                WHERE l.idversionproduct=%s
                ORDER BY c.logical_code, c.version
            """,
                [version_id],
            )

            cp = fetch_docs(
                """
                SELECT l.id link_id, c.id cp_id, d.id doc_id, c.logical_code, c.version, l.estado, l.vigencia,
                       d.nombre, d.mime, d.archivo_url, d.tamano, c.genera_prima
                FROM link.vp_to_cp l
                JOIN core.cp c ON c.id = l.idcp
                JOIN core.documento d ON d.id = c.documento_id
                WHERE l.idversionproduct=%s
                ORDER BY c.logical_code, c.version
            """,
                [version_id],
            )

            annex = fetch_docs(
                """
                SELECT l.id link_id, a.id annex_id, d.id doc_id, a.logical_code, a.version, l.estado, l.vigencia,
                       d.nombre, d.mime, d.archivo_url, d.tamano, a.genera_prima, a.tipo
                FROM link.vp_to_annex l
                JOIN core.annex a ON a.id = l.idannex
                JOIN core.documento d ON d.id = a.documento_id
                WHERE l.idversionproduct=%s
                ORDER BY a.logical_code, a.version
            """,
                [version_id],
            )

            fmt = fetch_docs(
                """
                SELECT l.id link_id, f.id format_id, d.id doc_id, f.logical_code, f.version, l.estado, l.vigencia,
                       d.nombre, d.mime, d.archivo_url, d.tamano, f.tipo
                FROM link.vp_to_format l
                JOIN core.format f ON f.id = l.idformat
                JOIN core.documento d ON d.id = f.documento_id
                WHERE l.idversionproduct=%s
                ORDER BY f.logical_code, f.version
            """,
                [version_id],
            )

            receipts = fetch_docs(
                """
                SELECT id, tipo, actor_id, created_at, doc_id, meta
                FROM workflow.receipt
                WHERE case_id IN (
                    SELECT id FROM workflow.case WHERE product_case_id=%s
                )
                ORDER BY created_at DESC
            """,
                [product_case_id],
            )

        return Response(
            {
                "header": {
                    "product_id": str(product_id),
                    "version_id": str(version_id),
                    "nombre": nombre,
                    "estado": estado,
                    "nro_version": nro_version,
                },
                "sections": {
                    "CG": cg,
                    "CP": cp,
                    "ANNEX": annex,
                    "FORMAT": fmt,
                },
                "timeline": receipts,
            }
        )
