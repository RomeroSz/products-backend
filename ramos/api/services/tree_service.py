# products-backend/ramos/api/services/tree_service.py
from typing import List, Dict, Any
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


def get_roots() -> List[Dict[str, Any]]:
    """
    Raíces (L1): parent_id IS NULL, ordenadas por attrs->>'ord', name
    """
    sql = """
    SELECT id, code, name, level, kind, is_active
    FROM ramo.node
    WHERE parent_id IS NULL
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name;
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [
        {"id": r[0], "code": r[1], "name": r[2], "level": r[3], "kind": r[4], "isActive": bool(r[5])}
        for r in rows
    ]


def get_children(parent_id: Any) -> List[Dict[str, Any]]:
    parent_id = _ensure_uuid(parent_id)
    sql = """
    SELECT id, code, name, level, kind, is_active
    FROM ramo.node
    WHERE parent_id = %s
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [parent_id])
        rows = cur.fetchall()
    return [
        {"id": r[0], "code": r[1], "name": r[2], "level": r[3], "kind": r[4], "isActive": bool(r[5])}
        for r in rows
    ]


def get_tree(depth: int = 3, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Árbol ligero hasta depth (default 3).
    Trae N1 y expande recursivamente hasta depth usando CTE.
    """
    # 1) Traer raíces limitadas
    roots_sql = """
    SELECT id, code, name, level, kind, is_active
    FROM ramo.node
    WHERE parent_id IS NULL
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name
    LIMIT %s;
    """
    with connection.cursor() as cur:
        cur.execute(roots_sql, [limit])
        roots = cur.fetchall()

    if depth == 1:
        return [
            {"id": r[0], "code": r[1], "name": r[2], "level": r[3], "kind": r[4], "isActive": bool(r[5]), "children": []}
            for r in roots
        ]

    # 2) Para cada root, correr CTE hasta la profundidad pedida
    out: List[Dict[str, Any]] = []
    for rt in roots:
        root_id, code, name, level, kind, is_active = rt

        sql_cte = """
        WITH RECURSIVE t AS (
          SELECT id, code, name, level, kind, parent_id, 1 AS d
          FROM ramo.node WHERE id = %s
          UNION ALL
          SELECT n.id, n.code, n.name, n.level, n.kind, n.parent_id, t.d + 1
          FROM ramo.node n
          JOIN t ON n.parent_id = t.id
          WHERE t.d < %s
        )
        SELECT id, code, name, level, kind, parent_id, d
        FROM t
        ORDER BY d, COALESCE((SELECT (attrs->>'ord')::int FROM ramo.node x WHERE x.id=t.id), 999), name;
        """

        with connection.cursor() as cur:
            cur.execute(sql_cte, [root_id, depth])
            rows = cur.fetchall()

        # Construir árbol (sólo hasta 'depth')
        by_id: Dict[str, Dict[str, Any]] = {}
        children_map: Dict[str, List[Dict[str, Any]]] = {}

        for rid, rcode, rname, rlevel, rkind, rparent, d in rows:
            node = {
                "id": rid,
                "code": rcode,
                "name": rname,
                "level": rlevel,
                "kind": rkind,
                "children": []
            }
            by_id[str(rid)] = node
            if rparent:
                children_map.setdefault(str(rparent), []).append(node)

        # Incrustar hijos
        for pid, kids in children_map.items():
            if pid in by_id:
                by_id[pid]["children"] = kids

        root_obj = by_id[str(root_id)]
        # anexar isActive del root original
        root_obj["isActive"] = bool(is_active)
        out.append(root_obj)

    return out
