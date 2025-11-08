# products-backend/ramos/api/services/validation_service.py
from typing import List, Dict, Any, Optional, Tuple
from django.db import connection
import re
import uuid

UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")
MOD_NAME_RX = re.compile(
    r"^(individual|colectivo(\s|$)|colectivo o flota)$", re.IGNORECASE)


def _ensure_uuid(u: Any) -> str:
    if isinstance(u, uuid.UUID):
        u = str(u)
    if not isinstance(u, str) or not UUID_RX.match(u.strip()):
        raise ValueError("UUID inválido.")
    return u.strip()


def _fetch_node(pid: str) -> Optional[Dict[str, Any]]:
    sql = "SELECT id, code, name, level, kind, parent_id, is_active FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        cur.execute(sql, [pid])
        row = cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "code": row[1], "name": row[2], "level": int(row[3]),
            "kind": row[4], "parent_id": row[5], "is_active": bool(row[6])}


def _fetch_modalidad(pid: str) -> Optional[Dict[str, Any]]:
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
    return {"id": row[0], "mod_code": (row[1] or "").upper(), "mod_name": row[2], "parent_node_id": row[3]}


def _fetch_nodes_in_order(path_ids: List[Any]) -> List[Dict[str, Any]]:
    if not path_ids:
        raise ValueError("pathIds requerido.")
    norm_ids = [_ensure_uuid(pid) for pid in path_ids]

    items: List[Dict[str, Any]] = []
    for pid in norm_ids:
        node = _fetch_node(pid)
        if node:
            items.append(node)
            continue
        mod = _fetch_modalidad(pid)
        if mod:
            if not items:
                raise ValueError("Path inválido: modalidad sin padre.")
            if str(items[-1]["id"]) != str(mod["parent_node_id"]):
                raise ValueError(
                    "El path no respeta la jerarquía padre→hijo. (400.PATH_BROKEN)")
            parent_level = int(items[-1]["level"])
            items.append({
                "id": mod["id"], "code": mod["mod_code"], "name": mod["mod_name"],
                "level": parent_level + 1, "kind": "OPTION",
                "parent_id": items[-1]["id"], "is_active": True,
                "meta": {"is_modalidad": True, "modalidad_code": mod["mod_code"]},
            })
            continue
        raise ValueError(f"id inválido: {pid}")
    return items


def _leaf_requires_modalities(node_id: Any) -> bool:
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


def _node_has_modalities(node_id: Any) -> bool:
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


def _first_modality_code_for_node(node_id: Any) -> Optional[str]:
    # Si un OPTION tiene pivote a IND/COL, tomamos la primera (normalmente solo habrá una)
    sql = """
    SELECT UPPER(m.code)
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.node_id = %s AND nm.is_enabled = true
      AND m.code IN ('IND','COL')
    ORDER BY m.code
    LIMIT 1
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        row = cur.fetchone()
    return row[0] if row else None


def _infer_modality_from_option_name(name: str) -> Optional[str]:
    n = (name or "").strip().lower()
    if n == "individual":
        return "IND"
    if n == "colectivo" or n == "colectivo o flota" or n.startswith("colectivo "):
        return "COL"
    return None


def validate_path_and_modalidades(path_ids: List[Any], modalidades: Optional[List[str]]) -> Dict[str, Any]:
    items = _fetch_nodes_in_order(path_ids)

    # integridad padre->hijo (respetando nm virtual)
    for i in range(1, len(items)):
        if items[i].get("meta", {}).get("is_modalidad"):
            continue
        if str(items[i]["parent_id"]) != str(items[i - 1]["id"]):
            raise ValueError(
                "El path no respeta la jerarquía padre→hijo. (400.PATH_BROKEN)")

    leaf = items[-1]

    # Caso 1: leaf es nm.id virtual -> ya lo manejamos como antes
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

    # Caso 2: leaf es un OPTION real que representa una modalidad (IND/COL)
    # Regla: si el OPTION tiene pivote IND/COL o su nombre coincide con Individual/Colectivo,
    #        NO pedimos modalidad; la inferimos.
    if (leaf["kind"] or "").upper() == "OPTION" and (_node_has_modalities(leaf["id"]) or MOD_NAME_RX.match(leaf["name"] or "")):
        inferred = _first_modality_code_for_node(
            leaf["id"]) or _infer_modality_from_option_name(leaf["name"]) or None
        if inferred is None:
            # si por alguna razón no logramos inferir, cae a la lógica general
            pass
        else:
            # allowed se toma del propio OPTION o de su padre si lo prefieres:
            allowed = _allowed_modalities(leaf["id"])
            if not allowed:
                # fallback al padre inmediato si el OPTION no tiene pivote propio
                allowed = _allowed_modalities(items[-2]["id"])
            return {
                "ok": True,
                "leaf": {"id": leaf["id"], "code": leaf["code"], "name": leaf["name"], "level": leaf["level"], "kind": leaf["kind"]},
                "levels": [it.get("level") for it in items],
                "codes": [it.get("code") for it in items],
                "requires_modalidad": False,          # <- CLAVE: no pedimos nada extra
                "allowed_modalidades": allowed or [],
                # <- CLAVE: inferido (IND o COL)
                "modalidades": [inferred],
            }

    # Caso 3: leaf normal (RAMO/SUBRAMO/OPTION no-modal)
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
