# products-backend/ramos/api/services/docs_service.py
from typing import List, Dict, Any, Set, Tuple
from django.db import connection

def _is_real_node(node_id: str) -> bool:
    sql = "SELECT 1 FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        return cur.fetchone() is not None

def _nm_parent(nm_id: str) -> str:
    sql = "SELECT node_id FROM ramo.node_modalidad WHERE id = %s AND is_enabled = TRUE"
    with connection.cursor() as cur:
        cur.execute(sql, [nm_id])
        row = cur.fetchone()
    return str(row[0]) if row else nm_id

def _effective_leaf_node_id(path: List[str]) -> str:
    leaf = path[-1]
    if _is_real_node(leaf):
        return leaf
    return _nm_parent(leaf)

def _docs_split_for_node(node_id: str) -> Tuple[List[str], List[str]]:
    """
    Retorna (uniform[], non_uniform[]) por node_id.
    """
    sql = """
    SELECT doc_type, is_uniform
    FROM ramo.doc_requirement
    WHERE node_id = %s
    ORDER BY doc_type
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        rows = cur.fetchall()
    uniform, non_uniform = [], []
    for d, u in rows:
        if bool(u):
            uniform.append(d)
        else:
            non_uniform.append(d)
    return uniform, non_uniform

def list_uniform_docs_for_node(node_id: str) -> Dict[str, Any]:
    uni, _non = _docs_split_for_node(node_id)
    return {"node_id": node_id, "uniform": uni}

def list_docs_flags_for_selection(paths: List[List[str]]) -> Dict[str, Any]:
    """
    Para cada path consideramos SOLO el leaf real (o padre de nm).
    Devuelve:
      { per_item:[{pathIds, uniform:[...], non_uniform:[...]}],
        all_uniform: bool }
    """
    per_item = []
    all_uniform = True
    for p in paths:
        leaf_real = _effective_leaf_node_id(p)
        uni, non = _docs_split_for_node(leaf_real)
        per_item.append({"pathIds": p, "uniform": uni, "non_uniform": non})
        if non:
            all_uniform = False
    return {"per_item": per_item, "all_uniform": all_uniform}
