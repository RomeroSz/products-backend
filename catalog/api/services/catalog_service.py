# products-backend/catalog/api/services/catalog_service.py
from typing import Any, Dict, List, Optional
from django.db import connection


def _row_to_item(r) -> Dict[str, Any]:
    # Asegura salida uniforme para el front
    return {
        "id": r[0],
        "type": r[1],
        "code": r[2],
        "name": r[3],
        "enabled": r[4],
        "parent_id": r[5],
        "level": r[6],
        "meta": r[7] or {},  # JSONB (attrs)
    }


def get_catalog_items(
    item_type: Optional[str] = None,
    parent_id: Optional[str] = None,
    enabled: Optional[bool] = True,          # <- default: solo activos
    include_roots: bool = False,              # <- default: NO raíces
    limit: int = 200,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    Reglas por defecto (según lo que pediste):
    - enabled=True si no se especifica.
    - include_roots=False: filtra (parent_id IS NOT NULL OR depth > 0) por defecto.
    - Siempre devuelve 'meta' con attrs intacto para leer atributos específicos desde el front.
    """
    base = """
        SELECT id,
               item_type AS type,
               code,
               name,
               is_active AS enabled,
               parent_id,
               depth AS level,
               attrs AS meta
          FROM catalog.item
         WHERE 1=1
    """
    conds = []
    params = []

    if item_type:
        conds.append("AND item_type = %s")
        params.append(item_type)

    # enabled por defecto True
    if enabled is True:
        conds.append("AND is_active = TRUE")
    elif enabled is False:
        conds.append("AND is_active = FALSE")
    # si enabled es None → no se filtra

    if parent_id:
        conds.append("AND parent_id = %s")
        params.append(parent_id)
    elif not include_roots:
        # Si no piden raíces, aplicamos tu filtro clásico de hojas / con padre
        conds.append("AND (parent_id IS NOT NULL OR depth > 0)")

    order = " ORDER BY COALESCE((attrs->>'ord')::int, 999), name LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    sql = base + "\n".join([""] + conds) + order

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    return [_row_to_item(r) for r in rows]
