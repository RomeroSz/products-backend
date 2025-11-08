# products-backend/ramos/api/services/commission_service.py
from typing import List, Dict, Any, Optional, Tuple
from django.db import connection

# -------- helpers de lectura básica --------


def _is_real_node(node_id: str) -> bool:
    sql = "SELECT 1 FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        return cur.fetchone() is not None


def _nm_parent_and_code(nm_id: str) -> Optional[Tuple[str, str]]:
    """
    Devuelve (parent_node_id, modalidad_code) para nm.id; o None si no existe/disabled.
    """
    sql = """
    SELECT nm.node_id, UPPER(m.code)
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.id = %s AND nm.is_enabled = TRUE
    """
    with connection.cursor() as cur:
        cur.execute(sql, [nm_id])
        row = cur.fetchone()
    return (str(row[0]), row[1]) if row else None


def _chain_up_ids(leaf_real_node_id: str) -> List[str]:
    sql = """
    WITH RECURSIVE chain AS (
      SELECT id, parent_id FROM ramo.node WHERE id = %s
      UNION ALL
      SELECT p.id, p.parent_id
      FROM ramo.node p JOIN chain c ON p.id = c.parent_id
    )
    SELECT id FROM chain
    """
    with connection.cursor() as cur:
        cur.execute(sql, [leaf_real_node_id])
        return [str(r[0]) for r in cur.fetchall()]


def _option_child_for_modality(parent_id: str, modality_code: str) -> Optional[str]:
    """
    Si existen OPTION hijos 'Individual' / 'Colectivo' / 'Colectivo o Flota', dales máxima especificidad.
    Nos guiamos por el nombre del OPTION para IND/COL.
    """
    targets = {
        "IND": ("individual%",),
        "COL": ("colectivo%", "colectivo o flota%")
    }.get((modality_code or "").upper(), ())
    if not targets:
        return None

    q_like = " OR ".join(["name ILIKE %s"] * len(targets))
    sql = f"""
      SELECT id
      FROM ramo.node
      WHERE parent_id=%s AND kind='OPTION' AND ({q_like})
      ORDER BY COALESCE((attrs->>'ord')::int, 999), name
      LIMIT 1
    """
    params = [parent_id] + list(targets)
    with connection.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return str(row[0]) if row else None

# -------- cálculo de comisión (sin modalidad_id en commission_rule) --------


def _min_cap_for_nodes(node_ids: List[str]) -> Optional[float]:
    """
    Devuelve el menor FIXED_PERCENT entre los node_ids dados (sin dimensión de modalidad).
    """
    if not node_ids:
        return None
    sql = """
    SELECT MIN((rule_value->>'percent')::float)
    FROM ramo.commission_rule
    WHERE node_id = ANY(%s)
      AND UPPER(rule_type) = 'FIXED_PERCENT'
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_ids])
        v = cur.fetchone()[0]
    return float(v) if v is not None else None


def _cap_for_leaf_with_modalities(leaf_real: str, mod_codes: List[str]) -> Optional[float]:
    """
    Precedencia sin columna modalidad_id:
      1) OPTION hijo que represente la modalidad por nombre (IND/COL) -> cap(OPTION)
      2) cap(leaf_real)
      3) cap(ancestros)

    Si se pasan varias modalidades, agregamos candidatos y devolvemos el MIN real disponible.
    """
    chain_ids = _chain_up_ids(leaf_real)
    if not chain_ids:
        return None

    candidates: List[float] = []

    # 1) OPTION específico por cada modalidad solicitada (si existe)
    for m in (mod_codes or []):
        opt_id = _option_child_for_modality(leaf_real, m)
        if opt_id:
            v = _min_cap_for_nodes([opt_id])
            if v is not None:
                candidates.append(v)

    # 2) leaf_real
    v_leaf = _min_cap_for_nodes([leaf_real])
    if v_leaf is not None:
        candidates.append(v_leaf)

    # 3) ancestros (excluyendo leaf)
    v_anc = _min_cap_for_nodes(chain_ids[1:])
    if v_anc is not None:
        candidates.append(v_anc)

    if not candidates:
        return None
    return min(candidates)


def _split_leaf_and_modalities(path_ids: List[str], modalidades_from_validation: Optional[List[str]]) -> Tuple[str, List[str]]:
    """
    Devuelve (leaf_real_node_id, modalidades_codes[]) resolviendo nm.id si aplica.
    Si validation trajo modalidades [] las usamos; si no, sólo cuando el leaf sea nm.id.
    """
    leaf = path_ids[-1]
    if _is_real_node(leaf):
        leaf_real = leaf
        mods = list(modalidades_from_validation or [])
        return leaf_real, mods

    # nm.id virtual:
    res = _nm_parent_and_code(leaf)
    if not res:
        # id inválido; devolvemos leaf tal cual y sin mods para que falle río arriba si corresponde
        return leaf, list(modalidades_from_validation or [])
    parent_id, mod_code = res
    mods = list(modalidades_from_validation or [mod_code])
    return parent_id, mods


def compute_commission_for_validated(validated_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    validated_items: [{ "pathIds":[...], "validation":{...} }, ...]
    Devuelve:
      { "per_item":[{pathIds, percent}], "cap_min": float|null }
    """
    per_item: List[Dict[str, Any]] = []
    caps: List[float] = []

    for it in validated_items:
        p = it["pathIds"]
        v = it.get("validation", {}) or {}
        mods = v.get("modalidades") or None

        leaf_real, mod_codes = _split_leaf_and_modalities(p, mods)
        cap = _cap_for_leaf_with_modalities(leaf_real, mod_codes or [])
        per_item.append({"pathIds": p, "percent": cap})

        if cap is not None:
            caps.append(cap)

    cap_min = min(caps) if caps else None
    return {"per_item": per_item, "cap_min": cap_min}


def compute_commission_for_node(node_id: str, modalidades: Optional[List[str]] = None) -> Optional[float]:
    """
    Útil para el nodo 'Combinado' (si lo hay). Toma las mismas reglas de precedencia,
    pero sin nm.id ni paths. Si se pasan modalidades, aplica min por modalidad
    (vía OPTION hijos si existen).
    """
    leaf_real = node_id
    return _cap_for_leaf_with_modalities(leaf_real, modalidades or [])
