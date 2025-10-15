from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from django.db import connection
import re
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Tipos válidos para el árbol de ramos
RAMO_TYPES = ("RAMO_TAX", "RAMO")

# ==========================
# Utilidades
# ==========================
UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def is_uuid(s: Optional[str]) -> bool:
    return bool(s) and bool(UUID_RX.match(str(s)))


def r_to_node(r: Tuple[Any, ...]) -> Dict[str, Any]:
    """Mapea una fila ya aliaseada al contrato JSON amigable."""
    return {
        "id": r[0],
        "type": r[1],
        "code": r[2],
        "name": r[3],
        "enabled": r[4],
        "parent_id": r[5],
        "level": r[6],
        "meta": r[7],
        "children": [],  # para el árbol completo
    }


def row_to_dict(r: Tuple[Any, ...]) -> Dict[str, Any]:
    return {
        "id": r[0],
        "type": r[1],
        "code": r[2],
        "name": r[3],
        "enabled": r[4],
        "parent_id": r[5],
        "level": r[6],
        "meta": r[7],
    }


def parse_meta(meta_in: Any) -> Dict[str, Any]:
    """
    Normaliza meta a dict:
      - None -> {}
      - str  -> intenta json.loads o {}
      - dict "char-map" (keys numéricas) -> recompone la cadena y parsea
      - dict normal -> tal cual
      - cualquier otro -> {}
    """
    if not meta_in:
        return {}
    if isinstance(meta_in, dict):
        keys = list(meta_in.keys())
        if keys and all(isinstance(k, str) and k.isdigit() for k in keys):
            # Posible “char-map” de JSONB ({"0":"{","1":"\"","2":"o"...})
            ordered = "".join(str(meta_in[k])
                              for k in sorted(keys, key=lambda x: int(x)))
            try:
                parsed = json.loads(ordered)
                # preserva pares no numéricos si existieran
                extra = {k: v for k, v in meta_in.items() if not (
                    isinstance(k, str) and k.isdigit())}
                if isinstance(parsed, dict):
                    parsed.update(extra)
                    return parsed
                return extra
            except Exception:
                return {k: v for k, v in meta_in.items() if not (isinstance(k, str) and k.isdigit())}
        return meta_in
    if isinstance(meta_in, str):
        s = meta_in.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    # cualquier otro tipo
    return {}


# ==========================
# Selectores SQL
# ==========================

def fetch_ramo_items() -> List[Tuple[Any, ...]]:
    q = """
    SELECT id, item_type AS type, code, name, is_active AS enabled,
           parent_id, depth AS level, attrs AS meta
    FROM catalog.item
    WHERE item_type IN ('RAMO_TAX','RAMO') AND is_active=true
    ORDER BY COALESCE((attrs->>'ord')::int, 999), name
    """
    with connection.cursor() as cur:
        cur.execute(q)
        return cur.fetchall()


def load_item_by_id(item_id: str) -> Optional[Dict[str, Any]]:
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, item_type AS type, code, name, is_active AS enabled,
                   parent_id, depth AS level, attrs AS meta
            FROM catalog.item
            WHERE id=%s
            """,
            [item_id],
        )
        row = cur.fetchone()
    return row_to_dict(row) if row else None


# ==========================
# Lógica de árbol y validaciones
# ==========================

def build_tree(rows: Iterable[Tuple[Any, ...]]) -> List[Dict[str, Any]]:
    """
    Construye un árbol limpio y jerárquico a partir de los datos.
    1. Construye la estructura inicial.
    2. PODA: Elimina nodos 'RAMO' que compiten con 'RAMO_TAX' en el mismo nivel.
    3. COLAPSA: Simplifica nodos 'RAMO_TAX' que solo contienen un único 'RAMO' (preservando name/meta).
    4. APLANA: Eleva los hijos del nodo 'GENERALES' al nivel raíz.
    5. Ordena raíces por meta.ord (si existe).
    """
    nodes = [r_to_node(r) for r in rows]
    by_id = {n["id"]: n for n in nodes}
    initial_roots: List[Dict[str, Any]] = []

    # Paso 1: Construcción inicial del árbol
    for n in nodes:
        pid = n["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["children"].append(n)
        else:
            initial_roots.append(n)

    all_nodes_in_tree = list(by_id.values())

    # Paso 2: Poda de Nodos Paralelos
    for node in all_nodes_in_tree:
        if node["type"] == "RAMO_TAX" and node["children"]:
            has_tax_children = any(
                c["type"] == "RAMO_TAX" for c in node["children"])
            if has_tax_children:
                node["children"] = [c for c in node["children"]
                                    if c["type"] == "RAMO_TAX"]

    # Paso 3: Colapso de nodos contenedores redundantes
    for node in all_nodes_in_tree:
        if (
            node["type"] == "RAMO_TAX"
            and len(node["children"]) == 1
            and node["children"][0]["type"] == "RAMO"
        ):
            child = node["children"][0]
            node["id"] = child["id"]
            node["type"] = child["type"]
            node["code"] = child["code"]
            node["name"] = child["name"]
            node["level"] = child["level"]
            node["meta"] = child.get("meta")
            node["children"] = []

    # Paso 4: Aplanar el nodo "Generales" para elevar sus hijos al nivel raíz
    final_roots: List[Dict[str, Any]] = []
    for root_node in initial_roots:
        if (root_node.get("code") or "").upper() == "GENERALES":
            final_roots.extend(root_node.get("children", []))
        else:
            final_roots.append(root_node)

    # Paso 5: Re-ordenar por meta.ord si existe
    def get_order(node: Dict[str, Any]) -> int:
        meta = parse_meta(node.get("meta"))
        try:
            return int(meta.get("ord", 999))
        except Exception:
            return 999

    final_roots.sort(key=get_order)
    return final_roots


def _meta_allows_modalidades(meta_in: Any) -> List[str]:
    """
    Devuelve el array de modalidades permitidas desde meta.allowedModalidades,
    normalizadas a upper y únicas. Si no existe, devuelve [].
    """
    meta = parse_meta(meta_in)
    allowed = meta.get("allowedModalidades")
    if not allowed or not isinstance(allowed, list):
        return []
    norm: List[str] = []
    seen = set()
    for v in allowed:
        if not isinstance(v, str):
            continue
        u = v.strip().upper()
        if u and u not in seen:
            norm.append(u)
            seen.add(u)
    return norm


def get_allowed_modalidades_for_path(path_items: List[Dict[str, Any]]) -> List[str]:
    """
    Sube por el path hoja→...→raíz buscando la primera aparición de meta.allowedModalidades.
    En cuanto la encuentra, la devuelve normalizada. Si en todo el path no existe, [].
    """
    for it in reversed(path_items):  # hoja primero
        allowed = _meta_allows_modalidades(it.get("meta"))
        if allowed:
            return allowed
    return []


def is_multi(meta_in: Any, code: Optional[str], name: Optional[str]) -> bool:
    """
    Reglas para exigir selección de modalidades:
      1) Si meta.allowedModalidades existe y no está vacío → exige modalidades.
      2) Si meta.multi === true → exige modalidades.
      3) Si en el nombre aparece '*' (tu notación) → exige modalidades.
      4) Si el code hace match con patrones históricos → exige modalidades.
    """
    m = parse_meta(meta_in)
    if _meta_allows_modalidades(m):  # 1)
        return True
    if m.get("multi") is True:       # 2)
        return True
    if name and "*" in name:         # 3)
        return True
    # 4) patrones de respaldo
    patterns = ("AP_IND", "AP_COL", "AP_OCV", "RC_VEH", "AUTO_CAS")
    return any(code and p in code for p in patterns)


def requires_level5(path_items: List[Dict[str, Any]]) -> bool:
    """
    Determina si una rama exige llegar a N5 (subcategoría/modo).
    Por código (TRANS, RTECN, COMB, AUTO_CAS, RC_VEH) o meta.cg === true
    en cualquier nodo del path.
    """
    codes = [it["code"] for it in path_items if it]
    metas = [parse_meta(it.get("meta")) for it in path_items if it]
    needs = any(c in ("TRANS", "RTECN", "COMB", "AUTO_CAS", "RC_VEH")
                for c in codes)
    if any(m.get("cg") is True for m in metas):
        needs = True
    return needs


# ==========================
# Vistas
# ==========================
@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_tree",
    responses={200: OpenApiResponse(description="Árbol completo N1→N5")},
)
class RamosTreeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = fetch_ramo_items()
        return Response(build_tree(rows))


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_children",
    parameters=[OpenApiParameter("parent_id", str, required=False)],
    responses={200: OpenApiResponse(
        description="Hijos directos de un nodo (o raíces)")},
)
class RamosChildrenView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        pid = request.GET.get("parent_id")
        if pid:
            if not is_uuid(pid):
                return Response({"detail": "parent_id inválido (uuid)"}, status=400)
            q = """
            SELECT id, item_type AS type, code, name, is_active AS enabled,
                   parent_id, depth AS level, attrs AS meta
            FROM catalog.item
            WHERE is_active=true AND item_type IN ('RAMO_TAX','RAMO') AND parent_id=%s
            ORDER BY COALESCE((attrs->>'ord')::int, 999), name
            """
            params = [pid]
        else:
            # raíces (N1)
            q = """
            SELECT id, item_type AS type, code, name, is_active AS enabled,
                   parent_id, depth AS level, attrs AS meta
            FROM catalog.item
            WHERE is_active=true AND item_type='RAMO_TAX' AND (depth=1 OR parent_id IS NULL)
            ORDER BY COALESCE((attrs->>'ord')::int, 999), name
            """
            params = []
        with connection.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return Response([r_to_node(r) for r in rows])


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_validate_path",
    request={
        "type": "object",
        "properties": {
            "path_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "modalidades": {"type": "array", "items": {"type": "string"}, "nullable": True},
        },
        "required": ["path_ids"],
    },
    responses={200: OpenApiResponse(
        description="Validación de trayectoria N1→N5")},
)
class RamosValidatePathView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        path_ids = request.data.get("path_ids") or []
        modalidades = request.data.get("modalidades") or []

        if not isinstance(path_ids, list) or not path_ids:
            return Response({"ok": False, "error": "path_ids requerido"}, status=400)
        if not all(is_uuid(pid) for pid in path_ids):
            return Response({"ok": False, "error": "path_ids debe contener UUIDs"}, status=400)

        # Cargar todos los nodos del path (en orden)
        items: List[Dict[str, Any]] = []
        with connection.cursor() as cur:
            for pid in path_ids:
                cur.execute(
                    """
                    SELECT id, item_type AS type, code, name, is_active AS enabled,
                           parent_id, depth AS level, attrs AS meta
                    FROM catalog.item
                    WHERE id=%s
                    """,
                    [pid],
                )
                row = cur.fetchone()
                if not row:
                    return Response({"ok": False, "error": f"id inválido: {pid}"}, status=400)
                items.append(row_to_dict(row))

        # Reglas: al menos hasta N3 (Ramo Actuarial)
        last_level = items[-1]["level"] or 0
        if last_level < 3:
            return Response(
                {"ok": False,
                    "error": "Debes llegar al menos al Nivel 3 (Ramo Actuarial)."},
                status=400,
            )

        # Si la rama requiere N4/N5, exigirlo
        if requires_level5(items) and last_level < 5:
            return Response(
                {"ok": False,
                    "error": "Esta rama exige llegar a Nivel 5 (subcategoría y/o modalidad)."},
                status=400,
            )

        # Validación de consistencia padre→hijo
        for i in range(1, len(items)):
            if items[i]["parent_id"] != items[i - 1]["id"]:
                return Response({"ok": False, "error": "El path no respeta la jerarquía padre→hijo."}, status=400)

        # Allowed modalidades desde el path (hoja→ancestros)
        allowed_modalidades = get_allowed_modalidades_for_path(items)

        # Normalizar modalidades de entrada a UPPER
        modalidades_in: List[str] = []
        if modalidades and isinstance(modalidades, list):
            for m in modalidades:
                if isinstance(m, str) and m.strip():
                    modalidades_in.append(m.strip().upper())

        # Validar modalidades cuando el leaf las requiera
        leaf = items[-1]
        requires_modalidad = is_multi(
            leaf.get("meta"), leaf.get("code"), leaf.get("name"))
        if requires_modalidad:
            # Si exige modalidad pero el path no define allowedModalidades → error de datos
            if not allowed_modalidades:
                return Response(
                    {
                        "ok": False,
                        "error": "Esta rama exige modalidades pero no hay allowedModalidades configurado en el path. "
                                 "Carga meta.allowedModalidades en el RAMO hoja o algún ancestro RAMO_TAX.",
                    },
                    status=400,
                )
            # Debe seleccionar al menos una
            if not modalidades_in:
                return Response({"ok": False, "error": "Selecciona al menos una modalidad (p.ej. IND/COL)."}, status=400)
            # Todas deben estar permitidas
            not_allowed = [
                m for m in modalidades_in if m not in allowed_modalidades]
            if not_allowed:
                return Response(
                    {
                        "ok": False,
                        "error": f"Modalidades no permitidas para este ramo: {', '.join(not_allowed)}",
                        "allowed_modalidades": allowed_modalidades,
                    },
                    status=400,
                )

        return Response(
            {
                "ok": True,
                "leaf": leaf,
                "levels": [it["level"] for it in items],
                "codes": [it["code"] for it in items],
                "requires_modalidad": requires_modalidad,
                "allowed_modalidades": allowed_modalidades,  # útil para la UI
                "modalidades": modalidades_in or None,
            }
        )


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_resolve_codes",
    request={
        "type": "object",
        "properties": {"path_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
        "required": ["path_codes"],
    },
    responses={200: OpenApiResponse(
        description="Convierte path por code → ids con validación padre→hijo")},
)
class RamosResolveCodesView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        path_codes = request.data.get("path_codes") or []
        if not path_codes:
            return Response({"error": "path_codes requerido"}, status=400)

        # Resolver secuencialmente por code y parent_id
        ids: List[str] = []
        parent = None
        with connection.cursor() as cur:
            for code in path_codes:
                if parent:
                    cur.execute(
                        """
                        SELECT id
                        FROM catalog.item
                        WHERE is_active=true AND item_type IN ('RAMO_TAX','RAMO')
                              AND code=%s AND parent_id=%s
                        LIMIT 1
                        """,
                        [code, parent],
                    )
                else:
                    # primer nivel puede no tener parent (RAMO_TAX raíz)
                    cur.execute(
                        """
                        SELECT id
                        FROM catalog.item
                        WHERE is_active=true AND item_type IN ('RAMO_TAX','RAMO') AND code=%s
                        ORDER BY depth ASC
                        LIMIT 1
                        """,
                        [code],
                    )
                row = cur.fetchone()
                if not row:
                    return Response({"error": f"code no resolvible en secuencia: {code}"}, status=400)
                ids.append(str(row[0]))
                parent = row[0]

        return Response({"path_ids": ids})


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_multi_rules",
    responses={200: OpenApiResponse(
        description="Nodos que permiten multiselección (por meta o patrón)")},
)
class RamosMultiRulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = """
        SELECT id, code, name, attrs AS meta
        FROM catalog.item
        WHERE is_active=true AND item_type IN ('RAMO_TAX','RAMO')
        """
        with connection.cursor() as cur:
            cur.execute(q)
            rows = cur.fetchall()

        multi = []
        for r in rows:
            _id, code, name, meta = r
            if is_multi(meta, code, name):
                multi.append({"id": _id, "code": code, "name": name})
        return Response(multi)


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_allowed_modalidades",
    request={
        "type": "object",
        "properties": {"path_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
        "required": ["path_ids"],
    },
    responses={200: OpenApiResponse(
        description="Modalidades permitidas (IND/COL/…) resueltas por path")},
)
class RamosAllowedModalidadesView(APIView):
    """
    Devuelve el array de modalidades permitidas para un path dado (hoja→ancestros).
    Útil para la UI: muestra chips si el array no está vacío.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        path_ids = request.data.get("path_ids") or []
        if not isinstance(path_ids, list) or not path_ids:
            return Response({"error": "path_ids requerido"}, status=400)
        if not all(is_uuid(pid) for pid in path_ids):
            return Response({"error": "path_ids debe contener UUIDs"}, status=400)

        # Cargar secuencialmente cada id (y respetar orden dado)
        items: List[Dict[str, Any]] = []
        for pid in path_ids:
            it = load_item_by_id(pid)
            if not it:
                return Response({"error": f"id inválido: {pid}"}, status=400)
            items.append(it)

        # Validación básica de jerarquía padre→hijo
        for i in range(1, len(items)):
            if items[i]["parent_id"] != items[i - 1]["id"]:
                return Response({"error": "El path no respeta la jerarquía padre→hijo."}, status=400)

        allowed = get_allowed_modalidades_for_path(items)
        return Response({"allowed_modalidades": allowed})


@extend_schema(
    tags=["Catalog"],
    operation_id="catalog_modalidades_list",
    responses={200: OpenApiResponse(
        description="Listado de modalidades (IND/COL/…)")},
)
class ModalidadesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = """
        SELECT id, item_type AS type, code, name, is_active AS enabled,
               parent_id, depth AS level, attrs AS meta
        FROM catalog.item
        WHERE item_type='MODALIDAD' AND is_active=true
        ORDER BY COALESCE((attrs->>'ord')::int, 999), name
        """
        with connection.cursor() as cur:
            cur.execute(q)
            rows = cur.fetchall()
        return Response(
            [
                {
                    "id": r[0],
                    "type": r[1],
                    "code": r[2],
                    "name": r[3],
                    "enabled": r[4],
                    "parent_id": r[5],
                    "level": r[6],
                    "meta": r[7],
                }
                for r in rows
            ]
        )
