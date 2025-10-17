# catalog/api/views/ramos_canonic.py
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
import re
import json

# ------------------------------------
# Helpers
# ------------------------------------


def _bool(v: Optional[str], default: bool) -> bool:
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in ("1", "true", "t", "yes", "y"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    return default


UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _is_uuid(s: Optional[str]) -> bool:
    return bool(s) and bool(UUID_RX.match(str(s)))


def _parse_combo_attrs(attrs: Any) -> Dict[str, Any]:
    """
    Normaliza rm.attrs (jsonb) a dict.
    Acepta:
      - dict (ok)
      - dict "char-map" (keys '0','1',...)  -> recompone y parsea
      - str (JSON)                          -> parsea
      - cualquier otro                      -> {}
    """
    if not attrs:
        return {}
    if isinstance(attrs, dict):
        keys = list(attrs.keys())
        if keys and all(isinstance(k, str) and k.isdigit() for k in keys):
            # Posible char-map de JSONB
            try:
                ordered = "".join(str(attrs[k]) for k in sorted(
                    keys, key=lambda x: int(x)))
                parsed = json.loads(ordered)
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
        return attrs
    if isinstance(attrs, str):
        s = attrs.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _looks_like_modality(code: Optional[str], name: Optional[str]) -> bool:
    """
    Detecta nodos metidos en la taxonomía que en realidad son "Individual/Colectivo".
    Los filtramos del path de presentación.
    """
    c = (code or "").strip().upper()
    n = (name or "").strip().upper()
    if c in ("IND", "COL"):
        return True
    if n in ("IND", "COL", "INDIVIDUAL", "COLECTIVO", "INDIVIDUAL *"):
        return True
    if "INDIVIDUAL" in n or "COLECTIVO" in n:
        return True
    return False


def _as_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    """
    Coacciona value a una lista de dicts con claves 'code','name','depth'.
    Acepta:
      - str (JSON) -> parsea a list
      - list[dict] -> lo valida/sanea
      - cualquier otro -> []
    """
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
        except Exception:
            return []
        if not isinstance(parsed, list):
            return []
        arr = parsed
    elif isinstance(value, list):
        arr = value
    else:
        return []

    out: List[Dict[str, Any]] = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        code = it.get("code")
        name = it.get("name")
        depth = it.get("depth")
        # normaliza mínimos
        if not isinstance(code, str):
            code = "" if code is None else str(code)
        if not isinstance(name, str):
            name = "" if name is None else str(name)
        try:
            d = int(depth) if depth is not None else None
        except Exception:
            d = None
        out.append({"code": code, "name": name, "depth": d})
    # Orden por depth si está disponible (raíz→hoja)
    out.sort(key=lambda x: (999 if x["depth"] is None else x["depth"]))
    return out


def _row_to_ramo_dict(r: Tuple[Any, ...]) -> Dict[str, Any]:
    # id, code, name, enabled, has_modalities, path_names
    return {
        "id": r[0],
        "code": r[1],
        "name": r[2],
        "isActive": r[3],
        "hasModalities": r[4],
        "path": r[5] or [],
    }

# ------------------------------------
# Views
# ------------------------------------


@extend_schema(
    tags=["Catalog · Ramos (Canónico)"],
    operation_id="catalog_ramos_list",
    parameters=[
        OpenApiParameter("active", bool, required=False),
        OpenApiParameter("q", str, required=False),
        OpenApiParameter("limit", int, required=False),
        OpenApiParameter("offset", int, required=False),
    ],
    responses={200: OpenApiResponse(
        description="Lista de ramos hoja canónica")},
)
class CatalogRamosListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active = _bool(request.GET.get("active"), True)
        q = (request.GET.get("q") or "").strip()
        try:
            limit = int(request.GET.get("limit") or 100)
            offset = int(request.GET.get("offset") or 0)
        except Exception:
            return Response({"detail": "limit/offset inválidos"}, status=400)

        where = ["i.item_type='RAMO'"]
        params: List[Any] = []

        if active:
            where.append("i.is_active=true")
        if q:
            where.append("(i.code ILIKE %s OR i.name ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like])

        # Solo hojas (sin hijos de ningún tipo)
        where.append(
            "NOT EXISTS (SELECT 1 FROM catalog.item ch WHERE ch.parent_id = i.id)")
        where_sql = " AND ".join(where)

        # Consulta sin intentar filtrar modalidades en SQL (las filtramos en Python)
        sql = f"""
        WITH base AS (
          SELECT
            i.id,
            i.code,
            i.name,
            i.is_active AS enabled,
            EXISTS (
              SELECT 1
              FROM core.ramo_modalidad rm
              WHERE rm.ramo_id = i.id AND rm.is_enabled = true
            ) AS has_modalities
          FROM catalog.item i
          WHERE {where_sql}
          ORDER BY COALESCE((i.attrs->>'ord')::int, 999), i.name
          LIMIT %s OFFSET %s
        ),
        paths AS (
          SELECT
            b.id AS ramo_id,
            (
              WITH RECURSIVE up AS (
                SELECT i2.id, i2.code, i2.name, i2.parent_id, i2.depth, i2.item_type
                FROM catalog.item i2
                WHERE i2.id = b.id
                UNION ALL
                SELECT p.id, p.code, p.name, p.parent_id, p.depth, p.item_type
                FROM catalog.item p
                JOIN up ON up.parent_id = p.id
                WHERE p.item_type = 'RAMO_TAX'
              )
              SELECT JSONB_AGG(JSONB_BUILD_OBJECT('code', code, 'name', name, 'depth', depth)
                               ORDER BY depth)
              FROM up
            ) AS path_objs
          FROM base b
        )
        SELECT
          b.id,
          b.code,
          b.name,
          b.enabled,
          b.has_modalities,
          COALESCE(p.path_objs, '[]'::jsonb) AS path_objs
        FROM base b
        LEFT JOIN paths p ON p.ramo_id = b.id;
        """

        with connection.cursor() as cur:
            cur.execute(sql, params + [limit, offset])
            rows = cur.fetchall()

        # total con mismos filtros
        sql_total = f"SELECT COUNT(1) FROM catalog.item i WHERE {where_sql}"
        with connection.cursor() as cur:
            cur.execute(sql_total, params)
            total = cur.fetchone()[0]

        # Limpieza del path en Python (filtrando modalidades “fantasma” y vacíos)
        items: List[Dict[str, Any]] = []
        for _id, code, name, enabled, has_mod, path_objs in rows:
            objs = _as_list_of_dicts(path_objs)  # parsea string JSONB / lista

            cleaned_names: List[str] = []
            for obj in objs:
                c = (obj.get("code") or "").strip()
                n = (obj.get("name") or "").strip()
                if not n:
                    continue
                if _looks_like_modality(c, n):
                    continue
                if not cleaned_names or cleaned_names[-1] != n:
                    cleaned_names.append(n)

            # Fallback: si el path se quedó vacío, al menos regresamos el propio nombre del ramo
            if not cleaned_names:
                cleaned_names = [name]

            items.append({
                "id": _id,
                "code": code,
                "name": name,
                "isActive": enabled,
                "hasModalities": has_mod,
                "path": cleaned_names,
            })

        return Response({"items": items, "total": total})


@extend_schema(
    tags=["Catalog · Ramos (Canónico)"],
    operation_id="ramos_modalidades",
    responses={200: OpenApiResponse(description="Modalidades por ramo")},
)
class RamoModalidadesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, ramo_id: str):
        if not _is_uuid(ramo_id):
            return Response({"detail": "ramo_id inválido (uuid)"}, status=400)

        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, name, is_active
                FROM catalog.item
                WHERE id=%s AND item_type='RAMO'
                """,
                [ramo_id],
            )
            row = cur.fetchone()
        if not row or row[3] is not True:
            return Response({"detail": "RAMO_NOT_FOUND"}, status=404)

        ramo = {"id": row[0], "code": row[1], "name": row[2]}

        sql = """
        SELECT
          m.id        AS modalidad_id,
          m.code      AS modalidad_code,
          m.name      AS modalidad_name,
          rm.attrs    AS combo_attrs
        FROM core.ramo_modalidad rm
        JOIN catalog.item m ON m.id = rm.modalidad_id
        WHERE rm.ramo_id = %s
          AND rm.is_enabled = true
          AND m.item_type = 'MODALIDAD'
          AND m.is_active = true
        ORDER BY COALESCE((m.attrs->>'ord')::int, 999), m.name
        """
        with connection.cursor() as cur:
            cur.execute(sql, [ramo_id])
            rows = cur.fetchall()

        modalidades: List[Dict[str, Any]] = []
        for mid, mcode, mname, combo_attrs in rows:
            display = mname
            mcode_u = (mcode or "").upper()
            if mcode_u == "COL":
                meta = _parse_combo_attrs(combo_attrs)
                label = meta.get("label_col")
                if isinstance(label, str) and label.strip():
                    display = label.strip()

            modalidades.append({
                "id": mid,
                "code": mcode_u,
                "name": mname,
                "displayName": display,
            })

        return Response({"ramo": ramo, "modalidades": modalidades})
