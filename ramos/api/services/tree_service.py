# products-backend/ramos/api/services/tree_service.py
from typing import List, Dict, Any, Optional, Set
from django.db import connection
import re
import uuid

# Acepta UUID con o sin guiones
UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _ensure_uuid(u: Any) -> str:
    if isinstance(u, uuid.UUID):
        u = str(u)
    if not isinstance(u, str) or not UUID_RX.match(u.strip()):
        raise ValueError("UUID inválido.")
    return u.strip()


def _fetch_id_by_code(code: str) -> Optional[str]:
    sql = "SELECT id FROM ramo.node WHERE code=%s"
    with connection.cursor() as cur:
        cur.execute(sql, [code])
        row = cur.fetchone()
    return str(row[0]) if row else None


def _presented_roots_ids() -> List[str]:
    """
    Orden de alto mando:
    1) Obligacionales o de responsabilidad   (GEN_OBL)
    2) Patrimoniales                         (GEN_PATR)
    3) Personas no Vida                      (GEN_PNV)
    4) Vida                                  (VID)
    """
    # padre GENERALES
    gen_id = _fetch_id_by_code("GEN")
    vid_id = _fetch_id_by_code("VID")
    if not vid_id:
        raise ValueError("Nodo 'VID' no encontrado.")
    if not gen_id:
        raise ValueError("Nodo 'GEN' no encontrado.")

    # hijos directos de GENERALES
    sql = """
    SELECT id, code
    FROM ramo.node
    WHERE parent_id = %s AND code IN ('GEN_OBL','GEN_PATR','GEN_PNV')
    """
    with connection.cursor() as cur:
        cur.execute(sql, [gen_id])
        rows = cur.fetchall()
    by_code = {r[1]: str(r[0]) for r in rows}

    for need in ("GEN_OBL", "GEN_PATR", "GEN_PNV"):
        if need not in by_code:
            raise ValueError(
                f"Nodo '{need}' no encontrado (hijo de GENERALES).")

    # orden solicitado
    return [by_code["GEN_OBL"], by_code["GEN_PATR"], by_code["GEN_PNV"], vid_id]


def _sr_allowed_ids(company_id: Optional[str]) -> Optional[Set[str]]:
    """
    Devuelve el conjunto de node_id visibles para la empresa (incluye descendientes),
    o None si no se quiere filtrar por SR.
    """
    if not company_id:
        return None

    company_id = _ensure_uuid(company_id)

    # 1) IDs aprobados explícitamente
    sql_approved = """
    SELECT n.id
    FROM ramo.sr_approval a
    JOIN ramo.node n ON n.id = a.node_id
    WHERE a.company_id = %s
    """
    with connection.cursor() as cur:
        cur.execute(sql_approved, [company_id])
        approved = [str(r[0]) for r in cur.fetchall()]

    if not approved:
        return set()  # nada visible

    # 2) Expandir descendientes (aprobación en L3 propaga a L4)
    sql_desc = """
    WITH RECURSIVE t AS (
      SELECT id FROM ramo.node WHERE id = ANY(%s)
      UNION ALL
      SELECT n.id
      FROM ramo.node n
      JOIN t ON n.parent_id = t.id
    )
    SELECT id FROM t;
    """
    with connection.cursor() as cur:
        cur.execute(sql_desc, [approved])
        rows = cur.fetchall()

    return {str(r[0]) for r in rows}


def _build_subtree(root_id: str, depth: int) -> Dict[str, Any]:
    """
    Construye árbol para un root hasta 'depth' usando CTE y agrega hints:
    - attrs (jsonb) del nodo
    - uniformDocs: ['CG','CP','RA', ...] donde is_uniform = true
    """
    sql_cte = """
    WITH RECURSIVE t AS (
      SELECT id, code, name, level, kind, parent_id, attrs, 1 AS d
      FROM ramo.node WHERE id = %s
      UNION ALL
      SELECT n.id, n.code, n.name, n.level, n.kind, n.parent_id, n.attrs, t.d + 1
      FROM ramo.node n
      JOIN t ON n.parent_id = t.id
      WHERE t.d < %s
    )
    SELECT
      id, code, name, level, kind, parent_id, d, attrs,
      COALESCE(
        (SELECT array_agg(dr.doc_type ORDER BY dr.doc_type)
           FROM ramo.doc_requirement dr
          WHERE dr.node_id = t.id AND dr.is_uniform = TRUE),
        ARRAY[]::text[]
      ) AS uniform_docs,
      COALESCE((SELECT (attrs->>'ord')::int FROM ramo.node x WHERE x.id=t.id), 999) AS ord
    FROM t
    ORDER BY d, ord, name;
    """

    with connection.cursor() as cur:
        cur.execute(sql_cte, [root_id, depth])
        rows = cur.fetchall()

    by_id: Dict[str, Dict[str, Any]] = {}
    children_map: Dict[str, List[Dict[str, Any]]] = {}

    # columnas: id, code, name, level, kind, parent_id, d, attrs, uniform_docs, ord
    for rid, rcode, rname, rlevel, rkind, rparent, d, rattrs, uniform_docs, _ord in rows:
        # Asegura dict python para attrs
        try:
            attrs_dict = dict(rattrs or {})
        except Exception:
            attrs_dict = {}

        # Insertamos nuestro hint en attrs sin pisar claves existentes
        if 'uniformDocs' not in attrs_dict:
            attrs_dict['uniformDocs'] = list(uniform_docs or [])

        node = {
            "id": rid,
            "code": rcode,
            "name": rname,
            "level": rlevel,
            "kind": rkind,
            "isActive": True,           # columna no existe en tu DB; asumimos activo
            "attrs": attrs_dict,        # <- importante para el front
            "children": []
        }
        by_id[str(rid)] = node
        if rparent:
            children_map.setdefault(str(rparent), []).append(node)

    for pid, kids in children_map.items():
        if pid in by_id:
            by_id[pid]["children"] = kids

    return by_id[str(root_id)]


def _filter_tree_by_allowed_ids(tree: Dict[str, Any], allowed: Set[str]) -> Optional[Dict[str, Any]]:
    """
    Devuelve el árbol filtrado a los ids permitidos. Si el root no tiene nada visible, devuelve None.
    """
    if str(tree["id"]) not in allowed:
        filtered_children = []
        for ch in tree.get("children", []):
            ft = _filter_tree_by_allowed_ids(ch, allowed)
            if ft:
                filtered_children.append(ft)
        if filtered_children:
            new_root = {**tree, "children": filtered_children}
            return new_root
        return None

    filtered_children = []
    for ch in tree.get("children", []):
        ft = _filter_tree_by_allowed_ids(ch, allowed)
        if ft:
            filtered_children.append(ft)
    return {**tree, "children": filtered_children}


def get_roots_presented() -> List[Dict[str, Any]]:
    """
    Raíces 'presentadas' con metadatos mínimos + attrs + uniformDocs.
    """
    root_ids = _presented_roots_ids()
    if not root_ids:
        return []
    sql = """
    SELECT id, code, name, level, kind, attrs
    FROM ramo.node
    WHERE id = ANY(%s)
    """
    with connection.cursor() as cur:
        cur.execute(sql, [root_ids])
        rows = cur.fetchall()

    by_id = {str(r[0]): r for r in rows}
    out = []
    for rid in root_ids:
        r = by_id[rid]
        rattrs = r[5]
        try:
            attrs_dict = dict(rattrs or {})
        except Exception:
            attrs_dict = {}
        # Raíz: normalmente no tendrá uniformDocs, pero dejamos la clave consistente
        attrs_dict.setdefault("uniformDocs", [])
        out.append({
            "id": r[0], "code": r[1], "name": r[2],
            "level": r[3], "kind": r[4],
            "isActive": True,
            "attrs": attrs_dict
        })
    return out

def get_roots(presented: bool = True, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Compat: lista raíces sin hijos.
    - presented=True → orden especial: [GEN_OBL, GEN_PATR, GEN_PNV, VID]
    - presented=False → parent_id IS NULL (orden por attrs->>'ord', name)
    """
    if presented:
        return get_roots_presented()

    sql = """
    SELECT id, code, name, level, kind
    FROM ramo.node
    WHERE parent_id IS NULL
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name
    LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [limit])
        rows = cur.fetchall()
    return [
        {"id": r[0], "code": r[1], "name": r[2],
            "level": r[3], "kind": r[4], "isActive": True}
        for r in rows
    ]


def get_children(parent_id: Any) -> List[Dict[str, Any]]:
    """
    Compat: hijos directos de un nodo (N+1).
    """
    pid = _ensure_uuid(parent_id)
    sql = """
    SELECT id, code, name, level, kind
    FROM ramo.node
    WHERE parent_id = %s
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [pid])
        rows = cur.fetchall()
    return [
        {"id": r[0], "code": r[1], "name": r[2],
            "level": r[3], "kind": r[4], "isActive": True}
        for r in rows
    ]


def get_tree(
    depth: int = 4,
    limit: int = 50,
    company_id: Optional[str] = None,
    presented: bool = True
) -> List[Dict[str, Any]]:
    """
    Árbol ligero hasta depth (default 4, para cubrir OPTIONS).
    - presented=True: raíces = [GEN_OBL, GEN_PATR, GEN_PNV, VID] (en ese orden).
    - SR filter: si company_id viene, se limita a lo aprobado (propagando a descendientes).
    """
    if presented:
        root_ids = _presented_roots_ids()
    else:
        # fallback clásico: parent_id IS NULL
        sql = """
        SELECT id
        FROM ramo.node
        WHERE parent_id IS NULL
        ORDER BY COALESCE((attrs->>'ord')::int, 999), name
        LIMIT %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [limit])
            root_ids = [str(r[0]) for r in cur.fetchall()]

    # None (sin filtro) | set() (nada) | set(ids)
    allowed = _sr_allowed_ids(company_id)

    out: List[Dict[str, Any]] = []
    for rid in root_ids:
        subtree = _build_subtree(rid, depth)
        if allowed is not None:
            filtered = _filter_tree_by_allowed_ids(subtree, allowed)
            if filtered:
                out.append(filtered)
        else:
            out.append(subtree)

    return out
