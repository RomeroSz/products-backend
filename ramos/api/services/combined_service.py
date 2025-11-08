# products-backend/ramos/api/services/combined_service.py
from typing import List, Dict, Any
from django.db import connection

def _n2_code_for_path(leaf_id: str) -> str:
    """
    Extrae el code de Nivel 2 (hijo de GEN o VID) para el leaf dado.
    """
    sql = """
    WITH RECURSIVE chain AS (
      SELECT id, code, name, parent_id, level FROM ramo.node WHERE id = %s
      UNION ALL
      SELECT p.id, p.code, p.name, p.parent_id, p.level
      FROM ramo.node p
      JOIN chain c ON p.id = c.parent_id
    )
    SELECT code FROM chain
    WHERE parent_id IN (SELECT id FROM ramo.node WHERE code IN ('GEN','VID'))
    LIMIT 1;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [leaf_id])
        row = cur.fetchone()
    return row[0] if row else ""

def _find_combined_node_under_n2(n2_code: str) -> Dict[str, Any]:
    """
    Busca el nodo L3 cuyo nombre/ código denote 'Combinad%' bajo el N2 dado.
    """
    sql = """
    SELECT l3.id, l3.code, l3.name
    FROM ramo.node n2
    JOIN ramo.node l3 ON l3.parent_id = n2.id
    WHERE n2.code = %s AND (l3.name ILIKE 'combinad%%' OR l3.code ILIKE %s)
    LIMIT 1;
    """
    like_code = f"{n2_code}_COMB%"
    with connection.cursor() as cur:
        cur.execute(sql, [n2_code, like_code])
        row = cur.fetchone()
    if not row:
        return {}
    return {"id": str(row[0]), "code": row[1], "name": row[2]}

def _list_options_for_combined(l3_comb_id: str) -> List[Dict[str, Any]]:
    sql = """
    SELECT id, code, name
    FROM ramo.node
    WHERE parent_id = %s
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name
    """
    with connection.cursor() as cur:
        cur.execute(sql, [l3_comb_id])
        rows = cur.fetchall()
    return [{"id": str(r[0]), "code": r[1], "name": r[2]} for r in rows]

def detect_combined_requirement(main_paths: List[List[str]]) -> Dict[str, Any]:
    """
    Regla: si hay >=2 ramos distintos dentro del MISMO N2 'GEN_PATR' o 'GEN_OBL',
    se requiere Combinado de ese N2 (opciones L4).
    """
    if not main_paths:
        return {"required": False}

    # Agrupamos por N2
    by_n2: Dict[str, set] = {}
    for p in main_paths:
        leaf = p[-1]
        n2 = _n2_code_for_path(leaf) or ""
        by_n2.setdefault(n2, set()).add(leaf)

    for n2, leaves in by_n2.items():
        if n2 in ("GEN_PATR", "GEN_OBL") and len(leaves) >= 2:
            l3_comb = _find_combined_node_under_n2(n2)
            options = _list_options_for_combined(l3_comb["id"]) if l3_comb else []
            return {
                "required": True,
                "n2_code": n2,
                "node": l3_comb or None,
                "options": options,
                "reason": "Seleccionaste 2 o más ramos del mismo N2"
            }
    return {"required": False}
