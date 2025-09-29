from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.db import connection, transaction


@dataclass
class CreateProductInput:
    nombre: str
    estado: str = "BORRADOR"
    tvpo: Optional[str] = None
    vigencia_desde: Optional[str] = None  # YYYY-MM-DD
    vigencia_hasta: Optional[str] = None  # YYYY-MM-DD or None
    modalidades: List[str] = None
    monedas: List[str] = None
    # [{"idramo": uuid, "is_principal": bool}]
    ramos: List[Dict[str, Any]] = None
    geo: List[str] = None
    tags: List[str] = None


@dataclass
class CreateProductResult:
    product_id: str
    version_id: str


def _insert_product(cur, nombre: str, estado: str) -> str:
    cur.execute(
        """
        INSERT INTO core.product (id, company_id, nombre, estado, created_at)
        VALUES (uuid_generate_v4(), current_setting('app.current_company_id')::uuid, %s, %s, now())
        RETURNING id
    """,
        [nombre, estado],
    )
    return cur.fetchone()[0]


def _insert_version(
    cur,
    product_id: str,
    tvpo: Optional[str],
    desde: Optional[str],
    hasta: Optional[str],
) -> str:
    cur.execute(
        """
        INSERT INTO core.version_product
        (id, idproduct, version, estado, locked_by_state, tvpo, vigencia_desde, vigencia_hasta, created_at)
        VALUES (uuid_generate_v4(), %s, 1, 'BORRADOR', false, %s, %s, %s, now())
        RETURNING id
    """,
        [product_id, tvpo, desde, hasta],
    )
    return cur.fetchone()[0]


def _bulk_insert_ids(cur, table: str, column_map: List[str], rows: List[List[Any]]):
    if not rows:
        return
    # simple ejecutor por filas (suficiente para MVP)
    sql = f"""
        INSERT INTO {table} ({", ".join(column_map)})
        VALUES ({", ".join(["%s"] * len(column_map))})
    """
    for r in rows:
        cur.execute(sql, r)


@transaction.atomic
def create_product_bundle(data: CreateProductInput) -> CreateProductResult:
    # Defaults
    data.modalidades = data.modalidades or []
    data.monedas = data.monedas or []
    data.ramos = data.ramos or []
    data.geo = data.geo or []
    data.tags = data.tags or []

    with connection.cursor() as cur:
        # Asegurar contexto DB (por si se llama fuera del request)
        # cur.execute('SELECT "security".set_context_from_user(%s)', [request.user.id])  # si aplica

        product_id = _insert_product(cur, data.nombre, data.estado)
        vp_id = _insert_version(
            cur, product_id, data.tvpo, data.vigencia_desde, data.vigencia_hasta
        )

        # Asociaciones básicas (dejan que los triggers validen)
        _bulk_insert_ids(
            cur,
            "core.product_version_modalidad",
            ["id", "idversionproduct", "idmodalidad"],
            [["uuid_generate_v4()", vp_id, mid] for mid in data.modalidades],
        )
        _bulk_insert_ids(
            cur,
            "core.product_version_moneda",
            ["id", "idversionproduct", "idmoneda"],
            [["uuid_generate_v4()", vp_id, mid] for mid in data.monedas],
        )
        _bulk_insert_ids(
            cur,
            "core.product_version_ramo",
            ["id", "idversionproduct", "idramo", "is_principal"],
            [
                ["uuid_generate_v4()", vp_id, r["idramo"], bool(r.get("is_principal"))]
                for r in data.ramos
            ],
        )
        _bulk_insert_ids(
            cur,
            "core.product_version_geo",
            ["id", "idversionproduct", "geo_id"],
            [["uuid_generate_v4()", vp_id, gid] for gid in data.geo],
        )
        _bulk_insert_ids(
            cur,
            "core.product_version_tag",
            ["id", "idversionproduct", "tag_id"],
            [["uuid_generate_v4()", vp_id, tid] for tid in data.tags],
        )

    return CreateProductResult(product_id=product_id, version_id=vp_id)
