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


def _fetch_node(pid: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT id, code, name, level, kind, parent_id, is_active
    FROM ramo.node
    WHERE id = %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [pid])
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "code": row[1], "name": row[2], "level": int(row[3]),
        "kind": row[4], "parent_id": row[5], "is_active": bool(row[6]),
    }


def _fetch_modalidad(pid: str) -> Optional[Dict[str, Any]]:
    """
    Si pid pertenece a ramo.node_modalidad, devuelve info de modalidad + su parent node.
    """
    sql = """
    SELECT nm.id, m.code, m.name, nm.node_id
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.id = %s AND nm.is_enabled = true
    """
    with connection.cursor() as cur:
        cur.execute(sql, [pid])
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],                    # id de node_modalidad
        "mod_code": (row[1] or "").upper(),
        "mod_name": row[2],
        # id del ramo/option padre en ramo.node
        "parent_node_id": row[3],
    }


def _fetch_nodes_in_order(path_ids: List[Any]) -> List[Dict[str, Any]]:
    """
    Construye la secuencia de elementos del path. El último puede ser:
      - un nodo real de ramo.node, o
      - una modalidad (ramo.node_modalidad) representada como OPTION 'virtual'.
    """
    if not path_ids:
        raise ValueError("pathIds requerido.")
    norm_ids = [_ensure_uuid(pid) for pid in path_ids]

    items: List[Dict[str, Any]] = []
    for i, pid in enumerate(norm_ids):
        node = _fetch_node(pid)
        if node:
            items.append(node)
            continue

        # ¿Es una modalidad (leaf virtual)?
        mod = _fetch_modalidad(pid)
        if mod:
            # Validar que haya al menos un item anterior y que el padre coincida
            if not items:
                raise ValueError("Path inválido: modalidad sin padre.")
            if str(items[-1]["id"]) != str(mod["parent_node_id"]):
                raise ValueError(
                    "El path no respeta la jerarquía padre→hijo. (400.PATH_BROKEN)")

            # Representamos modalidad como una 'hoja' OPTION virtual
            parent_level = int(items[-1]["level"])
            items.append({
                "id": mod["id"],                    # id de nm
                "code": mod["mod_code"],            # 'IND'|'COL'
                "name": mod["mod_name"],
                "level": parent_level + 1,
                "kind": "OPTION",
                "parent_id": items[-1]["id"],
                "is_active": True,
                "meta": {"is_modalidad": True, "modalidad_code": mod["mod_code"]},
            })
            continue

        # Si no es nodo ni modalidad conocida
        raise ValueError(f"id inválido: {pid}")

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
      - Padre→hijo consistente (el último puede ser una modalidad virtual OPTION).
      - Ya NO hay mínimo de nivel (permite ramos válidos en L2).
      - Si la hoja es modalidad virtual → se infiere automáticamente la modalidad.
      - Si la hoja es un RAMO con modalidades publicadas → exigir IND/COL.
    """
    items = _fetch_nodes_in_order(path_ids)

    # padre→hijo (solo entre nodos reales; la modalidad virtual se validó al insertar)
    for i in range(1, len(items)):
        # si current es virtual modalidad, ya verificamos el padre arriba
        if items[i].get("meta", {}).get("is_modalidad"):
            continue
        if str(items[i]["parent_id"]) != str(items[i - 1]["id"]):
            raise ValueError(
                "El path no respeta la jerarquía padre→hijo. (400.PATH_BROKEN)")

    leaf = items[-1]

    # ¿Leaf es modalidad virtual?
    if leaf.get("meta", {}).get("is_modalidad"):
        parent_id = items[-2]["id"]
        allowed = _allowed_modalities(parent_id)
        inferred = [leaf["meta"]["modalidad_code"]]
        if not inferred or any(m not in allowed for m in inferred):
            raise ValueError(
                "Modalidad no permitida para este ramo. (400.MODALITY_NOT_ALLOWED)")
        return {
            "ok": True,
            "leaf": {"id": leaf["id"], "code": leaf["code"], "name": leaf["name"], "level": leaf["level"], "kind": leaf["kind"]},
            "levels": [it.get("level") for it in items],
            "codes": [it.get("code") for it in items],
            "requires_modalidad": True,
            "allowed_modalidades": allowed,
            "modalidades": inferred,
        }

    # Si leaf es un nodo real
    requires_mod = _leaf_requires_modalities(leaf["id"])
    allowed = _allowed_modalities(leaf["id"]) if requires_mod else []

    modalidades_in: List[str] = []
    if modalidades and isinstance(modalidades, list):
        for m in modalidades:
            if isinstance(m, str) and m.strip():
                modalidades_in.append(m.strip().upper())

    if requires_mod:
        if not modalidades_in:
            raise ValueError(
                "Selecciona al menos una modalidad (IND/COL). (400.MODALITY_REQUIRED)")
        not_allowed = [m for m in modalidades_in if m not in allowed]
        if not_allowed:
            raise ValueError(
                f"Modalidades no permitidas para este ramo: {', '.join(not_allowed)} (400.MODALITY_NOT_ALLOWED)")

    return {
        "ok": True,
        "leaf": {"id": leaf["id"], "code": leaf["code"], "name": leaf["name"], "level": leaf["level"], "kind": leaf["kind"]},
        "levels": [it.get("level") for it in items],
        "codes": [it.get("code") for it in items],
        "requires_modalidad": requires_mod,
        "allowed_modalidades": allowed,
        "modalidades": modalidades_in or None,
    }
