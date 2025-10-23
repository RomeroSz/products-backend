# products-backend/ramos/api/services/ramos_flags_service.py
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection


def _fetch_chain_up(leaf_id: str) -> List[Dict[str, Any]]:
    """
    Trae el chain ascendente (leaf -> ... -> root) para un node_id dado.
    Devuelve una lista de dicts con: id, code, name, kind, parent_id, level_from_leaf (0 = leaf).
    """
    sql = """
    WITH RECURSIVE chain AS (
      SELECT
        n.id,
        n.code,
        n.name,
        n.kind,
        n.parent_id,
        0::int AS level_from_leaf
      FROM ramo.node n
      WHERE n.id = %(leaf_id)s

      UNION ALL

      SELECT
        p.id,
        p.code,
        p.name,
        p.kind,
        p.parent_id,
        c.level_from_leaf + 1
      FROM ramo.node p
      JOIN chain c ON p.id = c.parent_id
    )
    SELECT id, code, name, kind, parent_id, level_from_leaf
    FROM chain
    ORDER BY level_from_leaf ASC;
    """
    with connection.cursor() as cur:
        cur.execute(sql, {"leaf_id": leaf_id})
        rows = cur.fetchall()

    # columns: id, code, name, kind, parent_id, level_from_leaf
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "code": r[1],
                "name": r[2],
                "kind": r[3],
                "parent_id": r[4],
                "level_from_leaf": r[5],
            }
        )
    return out


def _looks_like_vida(node: Dict[str, Any]) -> bool:
    """
    Heurística ligera para detectar el ancla 'VIDA':
    - code == 'VID' (clásico)
    - o CATEGORY con code que empieza por 'VID'
    - o nombre que contiene 'Vida' (fallback seguro)
    """
    code = (node.get("code") or "").upper()
    name = (node.get("name") or "").strip().lower()
    kind = (node.get("kind") or "").upper()

    if code == "VID":
        return True
    if kind == "CATEGORY" and code.startswith("VID"):
        return True
    if name == "vida" or name.startswith("vida "):
        return True
    return False


def _pick_ramo_in_chain(chain: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Devuelve el nodo tipo RAMO más cercano al leaf (si existe).
    """
    for n in chain:  # chain viene leaf -> root
        if (n.get("kind") or "").upper() == "RAMO":
            return {"id": n["id"], "code": n["code"], "name": n["name"]}
    return None


def is_vida_by_path(path_ids: List[str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Dado un path (lista de UUIDs desde raíz→...→leaf o viceversa), determina:

    - bool is_vida: True si en la cadena de ancestros del leaf existe un ancla de VIDA
      (según heurística ligera).
    - dict ramo: el RAMO más cercano al leaf, si existe (id, code, name).

    Reglas:
    - Usamos el último elemento del path como leaf (pathIds[-1]), que es lo que
      envía el frontend en la mayoría de los árboles.
    - Lanza ValueError si el leaf no existe en DB.
    """
    if not path_ids or not isinstance(path_ids, list):
        raise ValueError("pathIds vacío o inválido")

    leaf_id = path_ids[-1]

    chain = _fetch_chain_up(leaf_id)
    if not chain:
        # Leaf no existe
        raise ValueError(f"node_id no encontrado: {leaf_id}")

    # ¿Hay ancla 'VIDA' en el chain?
    is_vida = any(_looks_like_vida(n) for n in chain)

    # ¿Cuál es el RAMO más cercano al leaf?
    ramo = _pick_ramo_in_chain(chain)

    return is_vida, ramo
