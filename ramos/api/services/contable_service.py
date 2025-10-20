# products-backend/ramos/api/services/contable_service.py
from typing import List, Dict, Any, Optional
from django.db import connection
import re
import uuid

# Acepta UUID con o sin guiones
UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _ensure_uuid(u: Any) -> str:
    """
    Acepta uuid.UUID o str; normaliza a str (canónica) y valida formato.
    """
    if isinstance(u, uuid.UUID):
        u = str(u)
    if not isinstance(u, str) or not UUID_RX.match(u.strip()):
        raise ValueError("UUID inválido.")
    return u.strip()


def _fetch_node_by_id(node_id: Any) -> Dict[str, Any]:
    node_id = _ensure_uuid(node_id)
    sql = "SELECT id, code, name, parent_id, kind, is_active FROM ramo.node WHERE id=%s"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        row = cur.fetchone()
    if not row:
        raise ValueError("Nodo no encontrado.")
    if not row[5]:
        raise ValueError("Nodo inactivo.")
    return {"id": row[0], "code": row[1], "name": row[2], "parent_id": row[3], "kind": row[4]}


def _fetch_node_by_code(code: str) -> Dict[str, Any]:
    sql = "SELECT id, code, name, parent_id, kind, is_active FROM ramo.node WHERE code=%s"
    with connection.cursor() as cur:
        cur.execute(sql, [code])
        row = cur.fetchone()
    if not row:
        raise ValueError("Nodo no encontrado (code).")
    if not row[5]:
        raise ValueError("Nodo inactivo.")
    return {"id": row[0], "code": row[1], "name": row[2], "parent_id": row[3], "kind": row[4]}


def _list_direct_mappings(node_id: Any) -> List[Dict[str, Any]]:
    node_id = _ensure_uuid(node_id)
    sql = """
    SELECT rtc.id, rc.id, rc.code, rc.name
    FROM accounting.ramo_to_contable rtc
    JOIN accounting.ramo_contable rc ON rc.id = rtc.idramo_contable
    WHERE rtc.node_id = %s
    ORDER BY rc.code;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        rows = cur.fetchall()
    return [{"id": r[0], "contable": {"id": r[1], "code": r[2], "name": r[3]}} for r in rows]


def list_mappings_for_node(node_code: Optional[str], node_id: Optional[Any]) -> List[Dict[str, Any]]:
    if node_id:
        node = _fetch_node_by_id(node_id)
    elif node_code:
        node = _fetch_node_by_code(node_code)
    else:
        raise ValueError("Debe enviar nodeCode o nodeId.")
    return _list_direct_mappings(str(node["id"]))


def create_mapping(node_id: Any, contable_code: str) -> Dict[str, Any]:
    node_id = _ensure_uuid(node_id)

    # Valida nodo
    _ = _fetch_node_by_id(node_id)

    # Valida contable_code
    sql_cont = "SELECT id, code, name FROM accounting.ramo_contable WHERE code=%s"
    with connection.cursor() as cur:
        cur.execute(sql_cont, [contable_code])
        rc = cur.fetchone()
    if not rc:
        raise ValueError("Código contable inexistente.")

    cont_id, cont_code, cont_name = rc

    # Evitar duplicados (unique node_id, idramo_contable)
    sql_exists = "SELECT id FROM accounting.ramo_to_contable WHERE node_id=%s AND idramo_contable=%s"
    with connection.cursor() as cur:
        cur.execute(sql_exists, [node_id, cont_id])
        row = cur.fetchone()
    if row:
        raise ValueError("409.MAPPING_ALREADY_EXISTS")

    # Insert
    sql_ins = "INSERT INTO accounting.ramo_to_contable (node_id, idramo_contable) VALUES (%s, %s) RETURNING id"
    with connection.cursor() as cur:
        cur.execute(sql_ins, [node_id, cont_id])
        new_id = cur.fetchone()[0]

    return {
        "id": new_id,
        "nodeId": node_id,
        "contable": {"id": cont_id, "code": cont_code, "name": cont_name},
    }


def delete_mapping(rtc_id: Any) -> None:
    rtc_id = _ensure_uuid(rtc_id)
    sql_sel = "SELECT id FROM accounting.ramo_to_contable WHERE id=%s"
    with connection.cursor() as cur:
        cur.execute(sql_sel, [rtc_id])
        row = cur.fetchone()
    if not row:
        raise ValueError("Mapping no encontrado.")

    sql_del = "DELETE FROM accounting.ramo_to_contable WHERE id=%s"
    with connection.cursor() as cur:
        cur.execute(sql_del, [rtc_id])


def bulk_insert_mappings(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Inserta nuevos vínculos. Si existe (node, contable) → lo reporta como skipped.
    """
    inserted, skipped, errors = [], [], []
    for r in rows:
        node_code = r.get("nodeCode")
        cont_code = r.get("contCode")
        if not node_code or not cont_code:
            errors.append({"row": r, "error": "row incompleto"})
            continue
        try:
            node = _fetch_node_by_code(node_code)
            try:
                mapping = create_mapping(str(node["id"]), cont_code)
                inserted.append(mapping)
            except ValueError as e:
                if "409." in str(e):
                    skipped.append({"row": r, "reason": "duplicate"})
                else:
                    errors.append({"row": r, "error": str(e)})
        except ValueError as e:
            errors.append({"row": r, "error": str(e)})

    return {"mode": "insert", "inserted": inserted, "skipped": skipped, "errors": errors}


def bulk_upsert_mappings(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Inserta vínculos y omite duplicados silenciosamente (efecto upsert).
    """
    inserted, skipped, errors = [], [], []
    for r in rows:
        node_code = r.get("nodeCode")
        cont_code = r.get("contCode")
        if not node_code or not cont_code:
            errors.append({"row": r, "error": "row incompleto"})
            continue
        try:
            node = _fetch_node_by_code(node_code)
            try:
                mapping = create_mapping(str(node["id"]), cont_code)
                inserted.append(mapping)
            except ValueError as e:
                if "409." in str(e):
                    skipped.append({"row": r, "reason": "duplicate"})
                else:
                    errors.append({"row": r, "error": str(e)})
        except ValueError as e:
            errors.append({"row": r, "error": str(e)})

    return {"mode": "upsert", "inserted": inserted, "skipped": skipped, "errors": errors}


def bulk_replace_mappings(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Reemplaza vínculos de los nodeCode presentes: borra los vínculos existentes del conjunto y vuelve a insertar.
    Operación acotada por los nodeCode enviados.
    """
    inserted, removed, errors = [], [], []

    # 1) Obtener IDs de nodos involucrados
    node_map: Dict[str, str] = {}
    for r in rows:
        if "nodeCode" in r:
            try:
                node = _fetch_node_by_code(r["nodeCode"])
                node_map[r["nodeCode"]] = str(node["id"])
            except ValueError as e:
                errors.append({"row": r, "error": str(e)})

    if not node_map:
        return {"mode": "replace", "inserted": inserted, "removed": removed, "errors": errors}

    # 2) Borrar vínculos existentes para los node_ids del set
    node_ids = list(node_map.values())
    sql_sel = """
    SELECT id FROM accounting.ramo_to_contable
    WHERE node_id = ANY(%s)
    """
    with connection.cursor() as cur:
        cur.execute(sql_sel, [node_ids])
        to_delete = [r[0] for r in cur.fetchall()]

    if to_delete:
        sql_del = "DELETE FROM accounting.ramo_to_contable WHERE id = ANY(%s)"
        with connection.cursor() as cur:
            cur.execute(sql_del, [to_delete])
        removed = to_delete

    # 3) Reinsertar (como insert normal)
    ins_result = bulk_insert_mappings(rows)
    inserted = ins_result.get("inserted", [])
    errors.extend(ins_result.get("errors", []))

    return {"mode": "replace", "inserted": inserted, "removed": removed, "errors": errors}


def _ascend_path(node_id: Any) -> List[str]:
    """
    Sube por parent_id hasta la raíz y devuelve la cadena [leaf, ..., root]
    """
    node_id = _ensure_uuid(node_id)
    chain: List[str] = []
    sql = "SELECT id, parent_id FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        current = node_id
        while current:
            cur.execute(sql, [current])
            row = cur.fetchone()
            if not row:
                break
            chain.append(str(row[0]))
            current = row[1]
    return chain  # leaf -> root


def resolve_contables_for_node(node_id: Any) -> Dict[str, Any]:
    node_id = _ensure_uuid(node_id)
    node = _fetch_node_by_id(node_id)

    chain = _ascend_path(node_id)
    seen = set()
    contables: List[Dict[str, Any]] = []

    sql = """
    SELECT rc.id, rc.code, rc.name
    FROM accounting.ramo_to_contable rtc
    JOIN accounting.ramo_contable rc ON rc.id = rtc.idramo_contable
    WHERE rtc.node_id = %s
    ORDER BY rc.code;
    """

    with connection.cursor() as cur:
        for nid in chain:  # leaf->...->root
            cur.execute(sql, [nid])
            rows = cur.fetchall()
            for r in rows:
                code = r[1]
                if code not in seen:
                    seen.add(code)
                    contables.append({"id": r[0], "code": r[1], "name": r[2]})

    source = "direct" if chain and contables and chain[0] == node_id else "inherited"
    return {
        "node": {"id": node["id"], "code": node["code"], "name": node["name"], "kind": node["kind"]},
        "contables": contables,
        "source": source
    }


def audit_unmapped_by_scope(scope: str) -> List[Dict[str, Any]]:
    """
    Detecta nodos sin ningún contable en su cadena ascendente.
    scope:
      - leaf     → nodos sin hijos (hojas)
      - ramo     → kind='RAMO'
      - category → kind='CATEGORY'
    """
    if scope == "leaf":
        base_sql = """
        WITH leaves AS (
          SELECT n.id, n.code, n.name, n.kind, n.parent_id, n.level
          FROM ramo.node n
          WHERE NOT EXISTS (SELECT 1 FROM ramo.node ch WHERE ch.parent_id = n.id)
        )
        SELECT id, code, name, kind, parent_id, level FROM leaves;
        """
    elif scope == "ramo":
        base_sql = "SELECT id, code, name, kind, parent_id, level FROM ramo.node WHERE kind='RAMO';"
    else:  # category
        base_sql = "SELECT id, code, name, kind, parent_id, level FROM ramo.node WHERE kind='CATEGORY';"

    with connection.cursor() as cur:
        cur.execute(base_sql)
        nodes = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for nid, code, name, kind, parent_id, level in nodes:
        chain = _ascend_path(str(nid))
        # ¿algún contable en la cadena?
        has_any = False
        sql_has = "SELECT 1 FROM accounting.ramo_to_contable WHERE node_id = %s LIMIT 1"
        with connection.cursor() as cur:
            for x in chain:
                cur.execute(sql_has, [x])
                if cur.fetchone():
                    has_any = True
                    break
        if not has_any:
            out.append({"id": str(nid), "code": code, "name": name, "kind": kind, "level": int(level)})

    return out
