# catalog/api/views/ramos.py
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiParameter
from django.db import connection
import json

RAMO_TYPES = ("RAMO_TAX", "RAMO")


def r_to_node(r):
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


def fetch_ramo_items():
    q = """
    SELECT id, type, code, name, enabled, parent_id, level, meta
    FROM catalog_item
    WHERE type IN ('RAMO_TAX','RAMO') AND enabled=true
    ORDER BY COALESCE((meta->>'ord')::int, 999), name
    """
    with connection.cursor() as cur:
        cur.execute(q)
        return cur.fetchall()


def build_tree(rows):
    nodes = [r_to_node(r) for r in rows]
    by_id = {n["id"]: n for n in nodes}
    roots = []
    for n in nodes:
        pid = n["parent_id"]
        if pid and pid in by_id:
            by_id[pid]["children"].append(n)
        else:
            # Nivel 1 (RAMO_TAX raíz) suele no tener parent
            roots.append(n)
    return roots


@extend_schema(tags=["Catalog · Ramos"], operation_id="catalog_ramos_tree",
               responses={200: OpenApiResponse(description="Árbol completo N1→N5")})
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
            q = """
            SELECT id, type, code, name, enabled, parent_id, level, meta
            FROM catalog_item
            WHERE enabled=true AND type IN ('RAMO_TAX','RAMO') AND parent_id=%s
            ORDER BY COALESCE((meta->>'ord')::int, 999), name
            """
            params = [pid]
        else:
            # raíces (N1)
            q = """
            SELECT id, type, code, name, enabled, parent_id, level, meta
            FROM catalog_item
            WHERE enabled=true AND type='RAMO_TAX' AND (level=1 OR parent_id IS NULL)
            ORDER BY COALESCE((meta->>'ord')::int, 999), name
            """
            params = []
        with connection.cursor() as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
        return Response([r_to_node(r) for r in rows])


def load_item_by_id(item_id):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT id, type, code, name, enabled, parent_id, level, meta
            FROM catalog_item WHERE id=%s
        """, [item_id])
        row = cur.fetchone()
    return row_to_dict(row) if row else None


def row_to_dict(r):
    return {
        "id": r[0], "type": r[1], "code": r[2], "name": r[3],
        "enabled": r[4], "parent_id": r[5], "level": r[6], "meta": r[7]
    }


def is_multi(meta, code, name):
    # Reglas de multiselección (las que marcaste con *) o por meta
    m = meta or {}
    if m.get("multi") is True:
        return True
    if name and "*" in name:
        return True
    # también por familia común
    patterns = ("AP_IND", "AP_COL", "AP_OCV", "RC_VEH", "AUTO_CAS")
    return any(code and p in code for p in patterns)


def requires_level5(path_items):
    """
    Determina si un path requiere llegar a N5 (p.ej. Transporte y combinaciones que exigen subrama y/o modalidad).
    Sugerencia: derivar por code meta.cg (cuando hay subcategorías obligatorias)
    """
    codes = [it["code"] for it in path_items if it]
    meta = [it["meta"] or {} for it in path_items if it]
    # ejemplo: Transporte (TRANS) y Ramos Técnicos (RTECN) tienen subniveles obligatorios (N4)
    needs = any(
        c in ("TRANS", "RTECN", "COMB", "AUTO_CAS", "RC_VEH")
        for c in codes
    )
    # si hay meta.cg y hay hijos, exigir descender
    if any(m.get("cg") is True for m in meta):
        needs = True
    return needs


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

        # Cargar todos los nodos del path (en orden)
        items = []
        with connection.cursor() as cur:
            for pid in path_ids:
                cur.execute("""
                    SELECT id, type, code, name, enabled, parent_id, level, meta
                    FROM catalog_item WHERE id=%s
                """, [pid])
                row = cur.fetchone()
                if not row:
                    return Response({"ok": False, "error": f"id inválido: {pid}"}, status=400)
                items.append(row_to_dict(row))

        # Reglas: al menos hasta N3 (Ramo Actuarial)
        last_level = items[-1]["level"] or 0
        if last_level < 3:
            return Response({"ok": False, "error": "Debes llegar al menos al Nivel 3 (Ramo Actuarial)."}, status=400)

        # Si la rama requiere N4/N5, exigirlo
        if requires_level5(items) and last_level < 5:
            return Response({"ok": False, "error": "Esta rama exige llegar a Nivel 5 (subcategoría y/o modalidad)."}, status=400)

        # Validación de consistencia padre→hijo
        for i in range(1, len(items)):
            if items[i]["parent_id"] != items[i - 1]["id"]:
                return Response({"ok": False, "error": "El path no respeta la jerarquía padre→hijo."}, status=400)

        # Validar modalidades cuando el leaf las requiera
        leaf = items[-1]
        if is_multi(leaf["meta"], leaf["code"], leaf["name"]) and not modalidades:
            return Response({"ok": False, "error": "Selecciona al menos una modalidad (IND/COL/...)."}, status=400)

        return Response({
            "ok": True,
            "leaf": leaf,
            "levels": [it["level"] for it in items],
            "codes": [it["code"] for it in items],
            "requires_modalidad": is_multi(leaf["meta"], leaf["code"], leaf["name"]),
        })


@extend_schema(
    tags=["Catalog · Ramos"],
    operation_id="catalog_ramos_resolve_codes",
    request={
        "type": "object",
        "properties": {
            "path_codes": {"type": "array", "items": {"type": "string"}, "minItems": 1}
        },
        "required": ["path_codes"]
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
        ids = []
        parent = None
        with connection.cursor() as cur:
            for code in path_codes:
                if parent:
                    cur.execute("""
                        SELECT id FROM catalog_item
                        WHERE enabled=true AND code=%s AND parent_id=%s
                        LIMIT 1
                    """, [code, parent])
                else:
                    # primer nivel puede no tener parent (RAMO_TAX raíz)
                    cur.execute("""
                        SELECT id FROM catalog_item
                        WHERE enabled=true AND code=%s
                        ORDER BY level ASC
                        LIMIT 1
                    """, [code])
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
        description="Nodos que permiten multiselección (por meta o patrón)")}
)
class RamosMultiRulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = """
        SELECT id, code, name, meta
        FROM catalog_item
        WHERE enabled=true AND type IN ('RAMO_TAX','RAMO')
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
    tags=["Catalog"],
    operation_id="catalog_modalidades_list",
    responses={200: OpenApiResponse(
        description="Listado de modalidades (IND/COL/…)")},
)
class ModalidadesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        q = """
        SELECT id, type, code, name, enabled, parent_id, level, meta
        FROM catalog_item
        WHERE type='MODALIDAD' AND enabled=true
        ORDER BY COALESCE((meta->>'ord')::int, 999), name
        """
        with connection.cursor() as cur:
            cur.execute(q)
            rows = cur.fetchall()
        return Response([{
            "id": r[0], "type": r[1], "code": r[2], "name": r[3],
            "enabled": r[4], "parent_id": r[5], "level": r[6], "meta": r[7],
        } for r in rows])
