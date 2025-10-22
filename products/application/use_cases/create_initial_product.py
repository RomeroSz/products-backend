from django.db import connection, transaction
from uuid import UUID

# --------------------------
# Helpers de bajo nivel SQL
# --------------------------


def _fetchone(cur):
    row = cur.fetchone()
    return row[0] if row else None


def _ensure_idempotency(idem_key: str) -> str | None:
    """
    Si ya existe un intento con esa clave, devuelve un JSON con {product_id, version_id, case_id}.
    Implementación base: usamos una tabla simple para idempotencia si la tienes.
    Si no la tienes aún, intenta detectar por (estado BORRADOR, company_id, nombre).
    """
    with connection.cursor() as cur:
        # Opción 1 (si creas una tabla auxiliar): idempotency(request_key TEXT PRIMARY KEY, result JSONB)
        cur.execute("""
            SELECT result::text
            FROM common.idempotency
            WHERE request_key = %s
        """, [idem_key])
        txt = _fetchone(cur)
        return txt


def _store_idempotency(idem_key: str, result_dict: dict):
    # Guarda resultado para la clave
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO common.idempotency(request_key, result)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (request_key) DO UPDATE SET result = EXCLUDED.result
        """, [idem_key, result_dict])


def _validate_ramo_path(path_ids: list[UUID]):
    # Valida existencia y cadena padre->hijo en ramo.node
    with connection.cursor() as cur:
        cur.execute("""
            SELECT id, parent_id FROM ramo.node WHERE id = ANY(%s)
        """, [path_ids])
        rows = cur.fetchall()
    if len(rows) != len(path_ids):
        raise ValueError("Ramo pathIds contiene IDs inexistentes en ramo.node")
    # Map id->parent
    parents = {r[0]: r[1] for r in rows}
    for i in range(1, len(path_ids)):
        if parents[path_ids[i]] != path_ids[i-1]:
            raise ValueError("Ramo pathIds no respeta jerarquía padre→hijo")


def _insert_product(company_id: UUID, nombre: str) -> UUID:
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.product (company_id, nombre)
            VALUES (%s, %s)
            RETURNING id
        """, [company_id, nombre])
        return _fetchone(cur)


def _insert_version(product_id: UUID) -> UUID:
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.version_product (idproduct, estado)
            VALUES (%s, 'BORRADOR'::product_version_state)
            RETURNING id
        """, [product_id])
        return _fetchone(cur)


def _insert_version_ramo(version_id: UUID, leaf_id: UUID, is_principal: bool):
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.product_version_ramo (idversionproduct, idramo, is_principal)
            VALUES (%s, %s, %s)
        """, [version_id, leaf_id, is_principal])


def _insert_documento(tipo: str, nombre: str, referencia_normativa: str | None, file: dict | None) -> UUID:
    archivo_url = file["url"] if file else None
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.documento (tipo, nombre, referencia_normativa, archivo_url, estado)
            VALUES (%s, %s, %s, %s, 'BORRADOR')
            RETURNING id
        """, [tipo, nombre, referencia_normativa, archivo_url])
        return _fetchone(cur)

# ---- ADAPTADORES: completa aquí el insert real a tus tablas cg/cp/annex/format ----


def _make_cg_from_documento(doc_id: UUID) -> UUID:
    """ Devuelve idcg. Rellena el INSERT correcto si core.cg requiere referencia al documento. """
    with connection.cursor() as cur:
        # TODO: ajusta a tu esquema real si cg tiene columna iddocumento
        cur.execute(
            """INSERT INTO core.cg (id) VALUES (%s) RETURNING id""", [doc_id])
        return _fetchone(cur)


def _make_cp_from_documento(doc_id: UUID, ramo_leaf_id: UUID | None) -> UUID:
    with connection.cursor() as cur:
        # Si tu CP exige ramo_id NOT NULL, usa ramo_leaf_id (del path enviado o del principal)
        cur.execute("""INSERT INTO core.cp (id, idramo) VALUES (%s, %s) RETURNING id""", [
                    doc_id, ramo_leaf_id])
        return _fetchone(cur)


def _make_annex_from_documento(doc_id: UUID, genera_prima: bool, ramo_leaf_id: UUID | None) -> UUID:
    with connection.cursor() as cur:
        cur.execute("""INSERT INTO core.annex (id, genera_prima, idramo) VALUES (%s, %s, %s) RETURNING id""",
                    [doc_id, genera_prima, ramo_leaf_id])
        return _fetchone(cur)


def _make_format_from_documento(doc_id: UUID) -> UUID:
    with connection.cursor() as cur:
        cur.execute(
            """INSERT INTO core.format (id) VALUES (%s) RETURNING id""", [doc_id])
        return _fetchone(cur)
# -----------------------------------------------------------------------------


def _link_vp_to_doc(table: str, version_id: UUID, doc_id: UUID):
    assert table in ("vp_to_cg", "vp_to_cp", "vp_to_annex", "vp_to_format")
    with connection.cursor() as cur:
        cur.execute(f"""
            INSERT INTO link.{table} (idversionproduct, {'idcg' if table == 'vp_to_cg' else 'idcp' if table == 'vp_to_cp' else 'idannex' if table == 'vp_to_annex' else 'idformat'}, vigencia, logical_version)
            VALUES (%s, %s, '(,)'::daterange, 1)
        """, [version_id, doc_id])


def _validate_actuario(cedula: str) -> None:
    if not cedula:
        return
    with connection.cursor() as cur:
        cur.execute("""
            SELECT 1
            FROM catalog.actuario_sut
            WHERE nacional_id = %s
              AND (estatus_vigencia IS NULL OR estatus_vigencia ILIKE 'VIGENTE')
        """, [cedula])
        if cur.fetchone() is None:
            raise ValueError("Actuario no vigente en catálogo SUT")


def _insert_ra(ra_data: dict) -> UUID:
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.ra (
                idmoneda, idtabla_mortalidad, idtipo_estudio,
                ga, it, utilidad_lim, tarifa_inmediata,
                vigencia_desde, vigencia_hasta, actuario_cedula, estado
            )
            VALUES (%(idmoneda)s, %(idtabla_mortalidad)s, %(idtipo_estudio)s,
                    %(ga)s, %(it)s, %(utilidad_lim)s, %(tarifa_inmediata)s,
                    %(vigencia_desde)s, %(vigencia_hasta)s, %(actuario_cedula)s, 'BORRADOR')
            RETURNING id
        """, ra_data)
        return _fetchone(cur)


def _link_ra_to_cp(ra_id: UUID, cp_ids: list[UUID]):
    if not cp_ids:
        return
    with connection.cursor() as cur:
        cur.executemany("""
            INSERT INTO link.ra_to_cp (idra, idcp, vigencia)
            VALUES (%s, %s, '(,)'::daterange)
        """, [(ra_id, cp) for cp in cp_ids])


def _link_ra_to_annex(ra_id: UUID, annex_ids: list[UUID]):
    if not annex_ids:
        return
    with connection.cursor() as cur:
        cur.executemany("""
            INSERT INTO link.ra_to_annex (idra, idannex, vigencia)
            VALUES (%s, %s, '(,)'::daterange)
        """, [(ra_id, an) for an in annex_ids])


def _open_product_case(product_id, sr_company_id) -> UUID | None:
    """Opcional: crea expediente. Si tu tabla define defaults, esto funciona."""
    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO core.product_case (product_id, sr_company_id, status)
            VALUES (%s, %s, 'DRAFT')
            RETURNING id
        """, [product_id, sr_company_id])
        return _fetchone(cur)

# --------------------------
# Caso de uso principal
# --------------------------


@transaction.atomic
def create_initial_product(payload: dict, user) -> dict:
    idem_key = payload["idempotency_key"]

    # Idempotencia (si tienes la tabla common.idempotency). Si no, comenta esto.
    cached = _ensure_idempotency(idem_key)
    if cached:
        return eval(cached)  # contenido seguro: JSON con ids

    # 1) Producto + versión
    p = payload["product"]
    nombre = p["nombre_comercial"] or p["nombre_tecnico"]
    product_id = _insert_product(p["company_id"], nombre)
    version_id = _insert_version(product_id)

    # 2) Ramos (usamos leaf_id = último de cada path)
    is_first = True
    main_leaf = None
    for r in payload["ramos"]:
        path = r["pathIds"]
        _validate_ramo_path(path)
        leaf = path[-1]
        if is_first:
            main_leaf = leaf
        _insert_version_ramo(version_id, leaf, is_principal=is_first)
        is_first = False

    # 3) CG
    cg = payload["cg"]
    if cg["uniform"]:
        doc_id = _insert_documento(
            "CG", f"CG uniforme - {nombre}", cg.get("referencia_normativa", None), None)
    else:
        doc_id = _insert_documento(
            "CG", f"CG - {nombre}", None, cg.get("file"))
    cg_id = _make_cg_from_documento(doc_id)
    _link_vp_to_doc("vp_to_cg", version_id, cg_id)

    # 4) CPs
    key_to_cp = {}
    for item in payload.get("cp", []):
        cp_doc_id = _insert_documento("CP", item["nombre"], None, item["file"])
        ramo_leaf = None
        if "ramo" in item and item["ramo"] and "pathIds" in item["ramo"]:
            _validate_ramo_path(item["ramo"]["pathIds"])
            ramo_leaf = item["ramo"]["pathIds"][-1]
        # fallback al ramo principal si tu schema obliga a idramo NOT NULL
        cp_id = _make_cp_from_documento(cp_doc_id, ramo_leaf or main_leaf)
        _link_vp_to_doc("vp_to_cp", version_id, cp_id)
        key_to_cp[item["key"]] = cp_id

    # 5) Annexes
    key_to_anx = {}
    for anx in payload.get("annexes", []):
        anx_doc_id = _insert_documento(
            "ANEXO", anx["nombre"], None, anx["file"])
        # Si anexos deben colgar del mismo ramo de la CP padre, úsalo:
        parent_cp_id = key_to_cp[anx["parent_cp"]]
        # puedes ajustar a ramo de la CP padre si tienes esa FK disponible
        ramo_leaf_for_annex = main_leaf
        anx_id = _make_annex_from_documento(
            anx_doc_id, anx["genera_prima"], ramo_leaf_for_annex)
        _link_vp_to_doc("vp_to_annex", version_id, anx_id)
        key_to_anx[anx["key"]] = anx_id

    # 6) RA[]
    for ra in payload.get("ra", []):
        data = dict(ra["data"])
        _validate_actuario(data.get("actuario_cedula", ""))
        ra_id = _insert_ra(data)
        _link_ra_to_cp(ra_id, [key_to_cp[k] for k in ra["targets"].get(
            "cp_keys", []) if k in key_to_cp])
        _link_ra_to_annex(ra_id, [key_to_anx[k] for k in ra["targets"].get(
            "annex_keys", []) if k in key_to_anx])
        # si quieres persistir files/supports a workflow.receipt, añade aquí tus INSERT a workflow.receipt

    # 7) Formats
    fm = payload["formats"]
    bas = fm.get("basicos", {})
    for nombre_k in ("solicitud", "cuadro"):
        if nombre_k in bas and bas[nombre_k]:
            fdoc = bas[nombre_k]
            fdoc_id = _insert_documento("FORMATO", fdoc["nombre"], None, fdoc)
            fid = _make_format_from_documento(fdoc_id)
            _link_vp_to_doc("vp_to_format", version_id, fid)
    for other in fm.get("otros", []):
        fdoc_id = _insert_documento("FORMATO", other["nombre"], None, other)
        fid = _make_format_from_documento(fdoc_id)
        _link_vp_to_doc("vp_to_format", version_id, fid)

    # (Opcional) expediente/caso
    case_id = _open_product_case(product_id, p["company_id"])

    result = {"product_id": str(product_id), "version_id": str(
        version_id), "case_id": str(case_id) if case_id else None}
    # guarda idempotencia si tienes la tabla
    try:
        _store_idempotency(idem_key, result)
    except Exception:
        pass
    return result
