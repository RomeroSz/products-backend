# products-backend/ramos/api/services/validation_service.py
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


def _fetch_nodes_in_order(path_ids: List[Any]) -> List[Dict[str, Any]]:
    if not path_ids:
        raise ValueError("pathIds requerido.")
    norm_ids = [_ensure_uuid(pid) for pid in path_ids]

    sql = """
    SELECT id, code, name, level, kind, parent_id, is_active
    FROM ramo.node
    WHERE id = %s
    """
    items: List[Dict[str, Any]] = []
    with connection.cursor() as cur:
        for pid in norm_ids:
            cur.execute(sql, [pid])
            row = cur.fetchone()
            if not row:
                raise ValueError(f"id inválido: {pid}")
            items.append({
                "id": row[0],
                "code": row[1],
                "name": row[2],
                "level": int(row[3]),
                "kind": row[4],
                "parent_id": row[5],
                "is_active": bool(row[6]),
            })
    return items


def _leaf_requires_modalities(node_id: Any) -> bool:
    node_id = _ensure_uuid(node_id)
    sql = """
    SELECT COUNT(1)
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.node_id = %s AND nm.is_enabled = true
      AND m.code IN ('IND','COL')
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        n = cur.fetchone()[0]
    return int(n or 0) > 0


def _allowed_modalities(node_id: Any) -> List[str]:
    node_id = _ensure_uuid(node_id)
    sql = """
    SELECT UPPER(m.code)
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.node_id = %s AND nm.is_enabled = true
      AND m.code IN ('IND','COL')
    ORDER BY m.code;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        rows = cur.fetchall()
    return [r[0] for r in rows]


def validate_path_and_modalidades(path_ids: List[Any], modalidades: Optional[List[str]]) -> Dict[str, Any]:
    """
    Reglas:
      - Mínimo nivel 3 (RAMO).
      - Padre→hijo consistente.
      - Si la hoja tiene modalidades publicadas → exigir al menos una y que pertenezcan al set permitido.
    """
    items = _fetch_nodes_in_order(path_ids)

    # padre→hijo
    for i in range(1, len(items)):
        if str(items[i]["parent_id"]) != str(items[i - 1]["id"]):
            raise ValueError("El path no respeta la jerarquía padre→hijo. (400.PATH_BROKEN)")

    leaf = items[-1]
    last_level = int(leaf["level"])
    if last_level < 3:
        raise ValueError("Debes llegar al menos al Nivel 3 (Ramo actuarial). (400.RAMO_MIN_LEVEL)")

    requires_mod = _leaf_requires_modalities(leaf["id"])
    allowed = _allowed_modalities(leaf["id"]) if requires_mod else []

    modalidades_in: List[str] = []
    if modalidades and isinstance(modalidades, list):
        for m in modalidades:
            if isinstance(m, str) and m.strip():
                modalidades_in.append(m.strip().upper())

    if requires_mod:
        if not modalidades_in:
            raise ValueError("Selecciona al menos una modalidad (IND/COL). (400.MODALITY_REQUIRED)")
        not_allowed = [m for m in modalidades_in if m not in allowed]
        if not_allowed:
            raise ValueError(f"Modalidades no permitidas para este ramo: {', '.join(not_allowed)} (400.MODALITY_NOT_ALLOWED)")

    return {
        "ok": True,
        "leaf": {"id": leaf["id"], "code": leaf["code"], "name": leaf["name"], "level": leaf["level"], "kind": leaf["kind"]},
        "levels": [it["level"] for it in items],
        "codes": [it["code"] for it in items],
        "requires_modalidad": requires_mod,
        "allowed_modalidades": allowed,
        "modalidades": modalidades_in or None,
    }
