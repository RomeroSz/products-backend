from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db import connection, transaction


@dataclass
class RACreateResult:
    ra_id: str
    case_id: str


@transaction.atomic
def create_ra_and_links(
    product_id: str,
    version_id: str,
    ra: Dict[str, Any],
    enlaces: Optional[Dict[str, List[str]]] = None,
) -> RACreateResult:
    enlaces = enlaces or {}
    with connection.cursor() as cur:
        # asegurar product_case y case
        cur.execute(
            "SELECT id FROM core.product_case WHERE product_id=%s", [product_id]
        )
        rr = cur.fetchone()
        if rr:
            product_case_id = rr[0]
        else:
            cur.execute(
                """
                INSERT INTO core.product_case (id, product_id, expediente_code, created_at, created_by_actor_id, status)
                VALUES (uuid_generate_v4(), %s, concat('EXP-', substr(uuid_generate_v4()::text,1,8)), now(),
                        current_setting('app.current_actor_id')::uuid, 'ABIERTO')
                RETURNING id
            """,
                [product_id],
            )
            product_case_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO workflow.case (id, version_product_id, estado, created_at, created_by_actor_id, product_case_id, meta)
            VALUES (uuid_generate_v4(), %s, 'ABIERTO', now(), current_setting('app.current_actor_id')::uuid, %s, '{}'::jsonb)
            RETURNING id
        """,
            [version_id, product_case_id],
        )
        case_id = cur.fetchone()[0]

        # crear RA
        cur.execute(
            """
            INSERT INTO core.ra
                (id, idmoneda, idtabla_mortalidad, idtipo_estudio, ga, it, utilidad_lim,
                 tarifa_inmediata, created_at, estado, vigencia_desde, vigencia_hasta, version)
            VALUES
                (uuid_generate_v4(), %s, %s, %s, %s, %s, %s,
                 %s, now(), 'BORRADOR', %s, %s, 1)
            RETURNING id
        """,
            [
                ra["idmoneda"],
                ra["idtabla_mortalidad"],
                ra["idtipo_estudio"],
                ra["ga"],
                ra["it"],
                ra["utilidad_lim"],
                ra["tarifa_inmediata"],
                ra.get("vigencia_desde"),
                ra.get("vigencia_hasta"),
            ],
        )
        ra_id = cur.fetchone()[0]

        # Enlaces RA ↔ CG/CP
        vrange = (
            f"[{ra['vigencia_desde']},{ra['vigencia_hasta']}]"
            if (ra.get("vigencia_desde") and ra.get("vigencia_hasta"))
            else (f"[{ra['vigencia_desde']},)" if ra.get("vigencia_desde") else "(,)")
        )
        for cg_id in enlaces.get("cg_ids", []):
            cur.execute(
                """
                INSERT INTO link.ra_to_annex (id, idra, idannex, tipo_enlace, compatibilidad, estado, vigencia)
                VALUES (uuid_generate_v4(), %s, %s, 'RA_CG', 'COMPATIBLE', 'VIGENTE', %s::daterange)
            """,
                [ra_id, cg_id, vrange],
            )  # NOTE: si usas otra tabla para RA↔CG cambia aquí

        for cp_id in enlaces.get("cp_ids", []):
            cur.execute(
                """
                INSERT INTO link.ra_to_cp (id, idra, idcp, tipo_enlace, compatibilidad, estado, vigencia, parametros_por_modalidad, ramos_involucrados, criterios_aplicabilidad)
                VALUES (uuid_generate_v4(), %s, %s, 'RA_CP', 'COMPATIBLE', 'VIGENTE', %s::daterange, '{}'::jsonb, '{}'::uuid[], '{}'::jsonb)
            """,
                [ra_id, cp_id, vrange],
            )

        # recibo
        cur.execute(
            """
            INSERT INTO workflow.receipt (id, case_id, tipo, actor_id, created_at, doc_id, meta)
            VALUES (uuid_generate_v4(), %s, 'RA', current_setting('app.current_actor_id')::uuid, now(), NULL,
                    jsonb_build_object('ra_id', %s))
        """,
            [case_id, ra_id],
        )

    return RACreateResult(ra_id=ra_id, case_id=case_id)
