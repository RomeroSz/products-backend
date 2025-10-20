# products-backend/ramos/api/services/tree_service.py
from typing import List, Dict, Any, Optional
from django.db import connection
import re
import uuid

from ramos.api.services.modalidad_service import list_modalidades_for_node

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
    SELECT id, code, name, level, kind, is_active, attrs
    FROM ramo.node
    WHERE parent_id IS NULL
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name;
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    return [
        {
            "id": r[0], "code": r[1], "name": r[2], "level": r[3],
            "kind": r[4], "isActive": bool(r[5]), "meta": r[6] or {}, "children": []
        }
        for r in rows
    ]


def get_children(parent_id: Any) -> List[Dict[str, Any]]:
    parent_id = _ensure_uuid(parent_id)
    sql = """
    SELECT id, code, name, level, kind, is_active, attrs
    FROM ramo.node
    WHERE parent_id = %s
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [parent_id])
        rows = cur.fetchall()
    return [
        {
            "id": r[0], "code": r[1], "name": r[2], "level": r[3],
            "kind": r[4], "isActive": bool(r[5]), "meta": r[6] or {}, "children": []
        }
        for r in rows
    ]


def _expand_modalidades_if_leaf(node: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """
    Si un nodo NO tiene hijos reales y posee modalidades publicadas (IND/COL),
    inyecta hijos virtuales de tipo OPTION (hojas) que representan las modalidades.
    """
    node_id = str(node["id"])
    # Si ya tiene hijos reales, no expandir modalidades aquí
    # (la expansión se hace solo sobre hojas reales)
    payload = list_modalidades_for_node(node_id)
    mods = payload.get("modalidades") or []
    if not mods:
        return None

    level = int(node.get("level") or 0)
    parent_code = str(node.get("code") or "")
    virtual_children: List[Dict[str, Any]] = []
    for m in mods:
        # Usamos el id de node_modalidad como ID del hijo virtual (estable)
        virtual_children.append({
            "id": m["id"],
            # puedes usar f"{parent_code}_{...}" si quieres evitar colisión global
            "code": (m.get("code") or "").upper(),
            "name": m.get("displayName") or m.get("name") or m.get("code"),
            "level": level + 1,
            "kind": "OPTION",
            "isActive": True,
            "meta": {
                "is_modalidad": True,
                "modalidad_code": (m.get("code") or "").upper(),
                "displayName": m.get("displayName") or m.get("name")
            },
            "children": []
        })

    return virtual_children


def get_tree(depth: int = 3, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Árbol ligero hasta depth (default 3).
    Trae N1 y expande recursivamente hasta depth usando CTE.
    Además, cuando una hoja no tiene hijos reales pero sí modalidades (IND/COL),
    inyecta nodos OPTION virtuales como hijos.
    """
    # 1) Traer raíces limitadas
    roots_sql = """
    SELECT id, code, name, level, kind, is_active, attrs
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
            {
                "id": r[0], "code": r[1], "name": r[2], "level": r[3],
                "kind": r[4], "isActive": bool(r[5]), "meta": r[6] or {}, "children": []
            }
            for r in roots
        ]

    # 2) Para cada root, correr CTE hasta la profundidad pedida
    out: List[Dict[str, Any]] = []
    for rt in roots:
        root_id, code, name, level, kind, is_active, attrs = rt

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
        SELECT id, code, name, level, kind, parent_id, attrs, d
        FROM t
        ORDER BY d, COALESCE((SELECT (attrs->>'ord')::int FROM ramo.node x WHERE x.id=t.id), 999), name;
        """

        with connection.cursor() as cur:
            cur.execute(sql_cte, [root_id, depth])
            rows = cur.fetchall()

        # Construir árbol (sólo hasta 'depth')
        by_id: Dict[str, Dict[str, Any]] = {}
        children_map: Dict[str, List[Dict[str, Any]]] = {}

        for rid, rcode, rname, rlevel, rkind, rparent, rattrs, d in rows:
            node = {
                "id": rid,
                "code": rcode,
                "name": rname,
                "level": rlevel,
                "kind": rkind,
                "isActive": True,
                "meta": rattrs or {},
                "children": []
            }
            by_id[str(rid)] = node
            if rparent:
                children_map.setdefault(str(rparent), []).append(node)

        # Incrustar hijos reales
        for pid, kids in children_map.items():
            if pid in by_id:
                by_id[pid]["children"] = kids

        root_obj = by_id[str(root_id)]
        root_obj["isActive"] = bool(is_active)

        # Inyección de modalidades como hijos virtuales SOLO para hojas reales
        for node_id, node in list(by_id.items()):
            if (node.get("children") or []):
                continue  # no es hoja
            # categoría terminal seleccionable (opcional): si quieres permitir CATEGORY sin hijos:
            # if node["kind"] == "CATEGORY" and (node.get("meta") or {}).get("selectable") is True:
            #     node["kind"] = "RAMO"
            virtual = _expand_modalidades_if_leaf(node)
            if virtual:
                # ahora el leaf se convierte en carpeta y sus hijos son OPTION (modalidad)
                node["children"] = virtual

        out.append(root_obj)
    return out
