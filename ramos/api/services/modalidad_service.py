# products-backend/ramos/api/services/modalidad_service.py
from typing import Dict, Any, List
from django.db import connection
import re
import uuid

UUID_RX = re.compile(r"^[0-9a-fA-F-]{36}$")


def _ensure_uuid(u: Any) -> str:
    """
    Acepta uuid.UUID o str; normaliza a str (canónica) y valida formato.
    """
    if isinstance(u, uuid.UUID):
        u = str(u)
    if not isinstance(u, str) or not UUID_RX.match(u.strip()):
        raise ValueError("UUID inválido.")
    return u.strip()


def _fetch_node(node_id: Any) -> Dict[str, Any]:
    node_id = _ensure_uuid(node_id)
    sql = "SELECT id, code, name, is_active FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        row = cur.fetchone()
    if not row or not row[3]:
        raise ValueError("Nodo inexistente o inactivo.")
    return {"id": row[0], "code": row[1], "name": row[2]}


def list_modalidades_for_node(node_id: Any) -> Dict[str, Any]:
    node_id = _ensure_uuid(node_id)
    ramo = _fetch_node(node_id)

    sql = """
    SELECT m.id, m.code, m.name, nm.attrs
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.node_id = %s AND nm.is_enabled = true
      AND m.code IN ('IND','COL')
    ORDER BY COALESCE((nm.attrs->>'ord')::int, 999), m.name;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        rows = cur.fetchall()

    modalidades: List[Dict[str, Any]] = []
    for mid, mcode, mname, attrs in rows:
        display = mname
        if (mcode or "").upper() == "COL" and isinstance(attrs, dict):
            label = attrs.get("label_col")
            if isinstance(label, str) and label.strip():
                display = label.strip()

        modalidades.append({
            "id": mid,
            "code": (mcode or "").upper(),
            "name": mname,
            "displayName": display
        })

    return {"node": ramo, "modalidades": modalidades}
