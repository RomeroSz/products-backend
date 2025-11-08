# products-backend/ramos/api/services/selection_preview_service.py
from typing import Any, Dict, List, Optional, Tuple, Set
from django.db import connection
import re
import uuid

UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _ensure_uuid(u: Any) -> str:
    if isinstance(u, uuid.UUID):
        u = str(u)
    if not isinstance(u, str) or not UUID_RX.match(u.strip()):
        raise ValueError("UUID inválido.")
    return u.strip()

# ---------- Helpers de DB ----------


def _fetch_node(node_id: str) -> Optional[Dict[str, Any]]:
    sql = "SELECT id, code, name, level, kind, parent_id, is_active FROM ramo.node WHERE id = %s"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "code": row[1], "name": row[2],
        "level": int(row[3]), "kind": row[4],
        "parent_id": row[5], "is_active": bool(row[6]),
    }


def _fetch_modalidad(nm_id: str) -> Optional[Dict[str, Any]]:
    sql = """
    SELECT nm.id, m.code, m.name, nm.node_id
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.id = %s AND nm.is_enabled = true
    """
    with connection.cursor() as cur:
        cur.execute(sql, [nm_id])
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0], "mod_code": (row[1] or "").upper(), "mod_name": row[2],
        "parent_node_id": row[3],
    }


def _fetch_chain_up(leaf_node_id: str) -> List[Dict[str, Any]]:
    sql = """
    WITH RECURSIVE chain AS (
      SELECT id, code, name, kind, parent_id, 0::int AS d
      FROM ramo.node WHERE id = %(leaf)s
      UNION ALL
      SELECT p.id, p.code, p.name, p.kind, p.parent_id, c.d + 1
      FROM ramo.node p JOIN chain c ON p.id = c.parent_id
    )
    SELECT id, code, name, kind, parent_id, d
    FROM chain ORDER BY d ASC
    """
    with connection.cursor() as cur:
        cur.execute(sql, {"leaf": leaf_node_id})
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({"id": r[0], "code": r[1], "name": r[2], "kind": r[3],
                    "parent_id": r[4], "d": int(r[5])})
    return out


def _family_from_chain(chain: List[Dict[str, Any]]) -> str:
    # VID tiene prioridad absoluta si aparece
    if any((n["code"] or "").upper() == "VID" for n in chain):
        return "VID"
    codes = {(n["code"] or "").upper() for n in chain}
    for f in ("GEN_PNV", "GEN_PATR", "GEN_OBL"):
        if f in codes:
            return f
    return "UNKNOWN"


def _uniform_docs_for(node_id: str) -> List[str]:
    sql = "SELECT doc_type FROM ramo.doc_requirement WHERE node_id = %s AND is_uniform = TRUE ORDER BY doc_type"
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        return [r[0] for r in cur.fetchall()]


def _node_requires_modalidad(node_id: str) -> Tuple[bool, List[str]]:
    sql = """
    SELECT UPPER(m.code)
    FROM ramo.node_modalidad nm
    JOIN ramo.modalidad m ON m.id = nm.modalidad_id
    WHERE nm.node_id = %s AND nm.is_enabled = true AND m.code IN ('IND','COL')
    ORDER BY m.code
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        rows = [r[0] for r in cur.fetchall()]
    return (len(rows) > 0, rows)


def _find_commission_specific_for_modalidad(ramo_id: str, modalidad_code: str) -> Optional[Tuple[float, Dict[str, Any]]]:
    """
    Busca una regla específica en OPTION hijo del ramo que coincida con IND/COL.
    Si encuentra, retorna (percent, source_node).
    """
    sql = """
    SELECT cr.rule_value->>'percent' AS pct, n.id, n.code, n.name, n.level, n.kind
    FROM ramo.node n
    JOIN ramo.commission_rule cr ON cr.node_id = n.id
    WHERE n.parent_id = %s
      AND n.kind = 'OPTION'
      AND (
           UPPER(n.code) LIKE %s
        OR UPPER(n.name) IN (%s,%s,%s) -- Individual / Colectivo / Colectivo o Flota
      )
    ORDER BY n.level DESC
    LIMIT 1
    """
    like = f"%_{modalidad_code.upper()}"
    name_ind = "INDIVIDUAL"
    name_col = "COLECTIVO"
    name_col2 = "COLECTIVO O FLOTA"
    with connection.cursor() as cur:
        cur.execute(sql, [ramo_id, like, name_ind, name_col, name_col2])
        row = cur.fetchone()
    if not row:
        return None
    pct = float(row[0])
    src = {"id": row[1], "code": row[2], "name": row[3],
           "level": int(row[4]), "kind": row[5]}
    return (pct, src)


def _find_commission_in_chain(leaf_or_ramo_id: str) -> Optional[Tuple[float, Dict[str, Any]]]:
    """
    Busca la primera regla de comisión en la cadena leaf->root.
    """
    chain = _fetch_chain_up(leaf_or_ramo_id)
    ids = [c["id"] for c in chain]  # leaf first
    sql = """
    SELECT cr.rule_value->>'percent' AS pct, n.id, n.code, n.name, n.level, n.kind
    FROM ramo.commission_rule cr
    JOIN ramo.node n ON n.id = cr.node_id
    WHERE n.id = ANY(%s)
    """
    with connection.cursor() as cur:
        cur.execute(sql, [ids])
        rows = cur.fetchall()
    if not rows:
        return None
    # Elegimos la más cercana al leaf
    by_id = {str(r[1]): r for r in rows}
    for nid in ids:
        if str(nid) in by_id:
            r = by_id[str(nid)]
            pct = float(r[0])
            src = {"id": r[1], "code": r[2], "name": r[3],
                   "level": int(r[4]), "kind": r[5]}
            return (pct, src)
    return None

# ---------- Núcleo de resolución por selection ----------


def _resolve_one_selection(path_ids: List[str]) -> Dict[str, Any]:
    if not path_ids:
        raise ValueError("pathIds requerido.")
    norm = [_ensure_uuid(x) for x in path_ids]

    items: List[Dict[str, Any]] = []
    # Construcción de secuencia, permitiendo leaf como modalidad virtual
    for i, pid in enumerate(norm):
        n = _fetch_node(pid)
        if n:
            if not n["is_active"]:
                raise ValueError("Nodo inactivo.")
            items.append(n)
            continue
        m = _fetch_modalidad(pid)
        if m:
            if not items:
                raise ValueError("Modalidad sin padre.")
            if str(items[-1]["id"]) != str(m["parent_node_id"]):
                raise ValueError("Path roto padre→hijo (modalidad).")
            parent = items[-1]
            items.append({
                "id": m["id"], "code": m["mod_code"], "name": m["mod_name"],
                "level": int(parent["level"]) + 1, "kind": "OPTION",
                "parent_id": parent["id"], "is_active": True,
                "meta": {"is_modalidad": True, "modalidad_code": m["mod_code"]}
            })
            continue
        raise ValueError(f"id inválido: {pid}")

    leaf = items[-1]
    # Validar encadenamiento real (saltando la hoja virtual si es modalidad)
    for i in range(1, len(items)):
        if items[i].get("meta", {}).get("is_modalidad"):
            continue
        if str(items[i]["parent_id"]) != str(items[i-1]["id"]):
            raise ValueError("Path roto padre→hijo.")

    # Ramo (más cercano al leaf)
    ramo = None
    for it in items:
        if (it["kind"] or "").upper() == "RAMO":
            ramo = it
            break
    if not ramo:
        # Si no hubo RAMO explícito en items, tomar el padre inmediato del leaf
        ramo_parent_id = leaf.get("parent_id")
        if ramo_parent_id:
            r = _fetch_node(str(ramo_parent_id))
            if r and (r["kind"] or "").upper() == "RAMO":
                ramo = r
    if not ramo:
        raise ValueError("No se ubicó el RAMO en la secuencia.")

    # Familia (VID / GEN_PNV / GEN_PATR / GEN_OBL)
    chain = _fetch_chain_up(ramo["id"])
    family = _family_from_chain(chain)

    # Docs uniformes (en leaf si es real; si es modalidad, tomar el RAMO)
    doc_node_id = leaf["id"] if not leaf.get(
        "meta", {}).get("is_modalidad") else ramo["id"]
    uniform_docs = _uniform_docs_for(str(doc_node_id))
    is_uniform_cp = ("CP" in uniform_docs)

    # Comisión
    is_modalidad = bool(leaf.get("meta", {}).get("is_modalidad"))
    modalidad_code = leaf.get("meta", {}).get(
        "modalidad_code") if is_modalidad else None

    commission_pct = None
    commission_src = None
    explain = None

    if is_modalidad and modalidad_code:
        # 1) buscar OPTION específico del ramo para la modalidad (IND/COL)
        got = _find_commission_specific_for_modalidad(
            str(ramo["id"]), modalidad_code)
        if got:
            commission_pct, commission_src = got
            explain = f"FIXED_PERCENT específico para modalidad {modalidad_code}"
        else:
            # 2) fallback: comisión del ramo (primera en cadena)
            got2 = _find_commission_in_chain(str(ramo["id"]))
            if got2:
                commission_pct, commission_src = got2
                explain = f"Fallback a comisión del RAMO (sin regla específica IND/COL)"
    else:
        # No es modalidad → tomar la primera de la cadena del leaf
        got = _find_commission_in_chain(str(leaf["id"]))
        if got:
            commission_pct, commission_src = got
            explain = "Regla más cercana leaf→root"

    if commission_pct is None:
        # último fallback: cadena desde RAMO
        got3 = _find_commission_in_chain(str(ramo["id"]))
        if got3:
            commission_pct, commission_src = got3
            explain = "Fallback a RAMO (no había en leaf)"

    # Modalidades publicadas en RAMO (para UX: si hace falta pedírselas)
    requires_mod, allowed_mods = _node_requires_modalidad(str(ramo["id"]))

    return {
        "pathIds": path_ids,
        "resolved": {
            "leaf": {"id": leaf["id"], "code": leaf["code"], "name": leaf["name"], "level": leaf["level"], "kind": leaf["kind"]},
            "ramo": {"id": ramo["id"], "code": ramo["code"], "name": ramo["name"]},
            "family": family,
            "is_modalidad": is_modalidad,
            "modalidad_code": modalidad_code,
            "requires_modalidad": (requires_mod and not is_modalidad),
            "allowed_modalidades": allowed_mods if (requires_mod and not is_modalidad) else []
        },
        "docs": {
            "uniform": uniform_docs,
            "is_uniform_cp": is_uniform_cp
        },
        "commission": {
            "cap_percent": float(commission_pct) if commission_pct is not None else None,
            "source_node": commission_src,
            "explain": explain
        }
    }

# ---------- Combinados ----------


PATR_COMBINADO_SUBCATS = [
    {"code": "RES", "name": "Residencial"},
    {"code": "IYC", "name": "Industria y comercio"},
    {"code": "COND", "name": "Condominio"},
    {"code": "TRI", "name": "Todo riesgo industrial"},
    {"code": "OTR", "name": "Otro Combinado"},
]


def _build_combined(selections: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Agrupar por family
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    for s in selections:
        fam = s["resolved"]["family"]
        by_family.setdefault(fam, []).append(s)

    out: Dict[str, Any] = {}
    for fam, arr in by_family.items():
        if fam == "VID":
            continue  # No hay combinado para Vida

        # Conjunto de ramos (ignorar IND/COL)
        rset: List[str] = []
        for s in arr:
            rid = str(s["resolved"]["ramo"]["id"])
            if rid not in rset:
                rset.append(rid)
        ramo_count = len(rset)

        # Si hay 2+ ramos diferentes, disparar combinado
        if ramo_count >= 2:
            # tope = min de cap_percent de esos ramos (si falta alguno, lo ignoramos)
            caps: List[float] = []
            seen_ramos: Set[str] = set()
            codes: List[str] = []
            for s in arr:
                rid = str(s["resolved"]["ramo"]["id"])
                if rid in seen_ramos:
                    continue
                seen_ramos.add(rid)
                codes.append(s["resolved"]["ramo"]["code"])
                cp = s["commission"]["cap_percent"]
                if isinstance(cp, (int, float)):
                    caps.append(float(cp))
            cap_percent = min(caps) if caps else None

            if fam == "GEN_PNV":
                out[fam] = {
                    "required": True,
                    "ramo_count": ramo_count,
                    "ramo_codes": codes,
                    "cap_percent": cap_percent,
                    "needs_modalidad_choice": True,
                    "allowed_modalidades": ["IND", "COL"]
                }
            elif fam == "GEN_PATR":
                out[fam] = {
                    "required": True,
                    "ramo_count": ramo_count,
                    "ramo_codes": codes,
                    "cap_percent": cap_percent,
                    "needs_subcategory_choice": True,
                    "subcategories": PATR_COMBINADO_SUBCATS
                }
            else:
                # GEN_OBL: aplicar la regla de mínimo, sin subcategoría adicional
                out[fam] = {
                    "required": True,
                    "ramo_count": ramo_count,
                    "ramo_codes": codes,
                    "cap_percent": cap_percent,
                    "note": "Combinado en Obligacionales: tope = menor comisión entre ramos."
                }
        else:
            # 1 solo ramo → podría haber múltiples modalidades; eso no es combinado.
            pass

    return out

# ---------- Anexos ----------


def _preview_annexes(annex: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not annex:
        return []
    out = []
    for a in annex:
        p = a.get("pathIds") or []
        sel = _resolve_one_selection(p)
        ramo = sel["resolved"]["ramo"]
        # Si CP es uniforme → el tope del anexo será el del ramo (cap_percent del ramo)
        # Calculamos tope del ramo por cadena (independiente de modalidad)
        rpct = None
        got = _find_commission_in_chain(str(ramo["id"]))
        if got:
            rpct = float(got[0])
        out.append({
            "pathIds": p,
            "ramo": ramo,
            "annex_rule": {
                "by": "CP_MIN",
                "cap_by_ramo_if_cp_uniform": rpct,
                "note": "La comisión del anexo no excede la definida en las CP; si las CP son RA general y uniforme, aplica el tope del ramo."
            }
        })
    return out

# ---------- Orquestador ----------


def build_selection_preview(payload: Dict[str, Any], company_id: Optional[str] = None) -> Dict[str, Any]:
    main = payload.get("main") or []
    if not isinstance(main, list) or not main:
        raise ValueError("'main' es requerido y debe ser lista.")

    selections: List[Dict[str, Any]] = []
    for item in main:
        p = item.get("pathIds") or []
        selections.append(_resolve_one_selection(p))

    combined = _build_combined(selections)
    annex = _preview_annexes(payload.get("annex"))

    return {
        "selections": selections,
        "combined": combined or None,
        "annex": annex or None
    }
