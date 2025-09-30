from dataclasses import dataclass
from typing import Optional
from django.db import connection


@dataclass
class WizardStatus:
    product_id: str
    version_id: str
    product_case_id: Optional[str]
    cg_count: int
    cp_count: int
    annex_count: int
    format_count: int
    ra_count: int
    can_validate: bool
    is_locked: bool
    estado: str


def get_wizard_status(version_id: str) -> WizardStatus:
    with connection.cursor() as cur:
        cur.execute(
            "SELECT idproduct, estado, locked_by_state FROM core.version_product WHERE id=%s", [version_id])
        row = cur.fetchone()
        if not row:
            raise ValueError("version no encontrada")
        product_id, estado, locked = row

        cur.execute(
            "SELECT id FROM core.product_case WHERE product_id=%s", [product_id])
        pc = cur.fetchone()
        product_case_id = pc[0] if pc else None

        cur.execute(
            "SELECT count(*) FROM link.vp_to_cg WHERE idversionproduct=%s", [version_id])
        cg_count = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM link.vp_to_cp WHERE idversionproduct=%s", [version_id])
        cp_count = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM link.vp_to_annex WHERE idversionproduct=%s", [version_id])
        annex_count = cur.fetchone()[0]

        cur.execute(
            "SELECT count(*) FROM link.vp_to_format WHERE idversionproduct=%s", [version_id])
        format_count = cur.fetchone()[0]

        # acota si RA se asocia a versión
        cur.execute(
            "SELECT count(*) FROM core.ra WHERE estado IN ('BORRADOR','VIGENTE','PUBLICADO')")
        ra_count = cur.fetchone()[0]

        # regla mínima; ajusta si necesitas.
        can_validate = (cg_count > 0 and cp_count > 0)

    return WizardStatus(
        product_id=str(product_id),
        version_id=str(version_id),
        product_case_id=product_case_id,
        cg_count=cg_count,
        cp_count=cp_count,
        annex_count=annex_count,
        format_count=format_count,
        ra_count=ra_count,
        can_validate=can_validate,
        is_locked=bool(locked),
        estado=estado,
    )
