from dataclasses import dataclass
from typing import List

from django.db import connection, transaction


@dataclass
class WizardStartResult:
    product_id: str
    version_id: str
    case_id: str
    product_case_id: str


@transaction.atomic
def wizard_start(
    company_id: str,
    nombre_comercial: str,
    nombre_tecnico: str,
    ramos_actuariales: List[str],
    ramos_contables: List[str],
    monedas: List[str],
    modalidades: List[str],
) -> WizardStartResult:
    with connection.cursor() as cur:
        # Crear product
        cur.execute(
            """
            INSERT INTO core.product (id, company_id, nombre, nombre_norm, created_at, estado, search_tsv)
            VALUES (uuid_generate_v4(), %s, %s, core.fn_normalize_text(%s), now(), 'BORRADOR', NULL)
            RETURNING id
        """,
            [company_id, nombre_comercial, nombre_comercial],
        )
        product_id = cur.fetchone()[0]

        # Crear versión
        cur.execute(
            """
            INSERT INTO core.version_product (id, idproduct, version, estado, locked_by_state, created_at)
            VALUES (uuid_generate_v4(), %s, 1, 'BORRADOR', false, now())
            RETURNING id
        """,
            [product_id],
        )
        version_id = cur.fetchone()[0]

        # Relaciones base
        for idramo in ramos_actuariales:
            cur.execute(
                """
                INSERT INTO core.product_version_ramo (id, idversionproduct, idramo, is_principal)
                VALUES (uuid_generate_v4(), %s, %s, false)
            """,
                [version_id, idramo],
            )

        for idramo_c in ramos_contables:
            cur.execute(
                """
                INSERT INTO accounting.ramo_to_contable (id, idramo, idramo_contable)
                VALUES (uuid_generate_v4(), %s, %s)
            """,
                [ramos_actuariales[0], idramo_c],
            )  # mapeo simple mínimo (ajústalo si requieres UI)

        for idmoneda in monedas:
            cur.execute(
                """
                INSERT INTO core.product_version_moneda (id, idversionproduct, idmoneda)
                VALUES (uuid_generate_v4(), %s, %s)
            """,
                [version_id, idmoneda],
            )

        for idmodalidad in modalidades:
            cur.execute(
                """
                INSERT INTO core.product_version_modalidad (id, idversionproduct, idmodalidad)
                VALUES (uuid_generate_v4(), %s, %s)
            """,
                [version_id, idmodalidad],
            )

        # Portada de expediente
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

        # Case de workflow (tramite)
        cur.execute(
            """
            INSERT INTO workflow.case (id, version_product_id, estado, created_at, created_by_actor_id, product_case_id, meta)
            VALUES (uuid_generate_v4(), %s, 'ABIERTO', now(), current_setting('app.current_actor_id')::uuid, %s, '{}'::jsonb)
            RETURNING id
        """,
            [version_id, product_case_id],
        )
        case_id = cur.fetchone()[0]

    return WizardStartResult(
        product_id=product_id,
        version_id=version_id,
        case_id=case_id,
        product_case_id=product_case_id,
    )
