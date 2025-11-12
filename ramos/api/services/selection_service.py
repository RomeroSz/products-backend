# products-backend/ramos/api/services/selection_service.py
from typing import Dict, Any, List, Optional
from ramos.api.services.validation_service import validate_path_and_modalidades
from ramos.api.services.ramos_flags_service import _fetch_chain_up
from ramos.api.services.combined_service import detect_combined_requirement
from ramos.api.services.docs_service import list_docs_flags_for_selection
from django.db import connection
from ramos.api.services.commission_service import (
    compute_commission_for_validated,
    compute_commission_for_node,
)


def _effective_leaf_node_id(leaf_id: str) -> str:
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM ramo.node WHERE id = %s", [leaf_id])
        if cur.fetchone():
            return leaf_id
        cur.execute(
            "SELECT node_id FROM ramo.node_modalidad WHERE id=%s AND is_enabled=TRUE", [leaf_id])
        row = cur.fetchone()
        return str(row[0]) if row else leaf_id


def _ramo_of(path: List[str]) -> Optional[Dict[str, Any]]:
    return _closest_ramo_in_chain(_effective_leaf_node_id(path[-1]))


def _closest_ramo_in_chain(path_leaf_id: str) -> Optional[Dict[str, Any]]:
    chain = _fetch_chain_up(path_leaf_id)
    for n in chain:  # leaf -> root
        if (n.get("kind") or "").upper() == "RAMO":
            return {"id": n["id"], "code": n["code"], "name": n["name"]}
    return None


def _normalize_paths(paths: List[List[str]]) -> List[List[str]]:
    if not isinstance(paths, list) or any(not isinstance(p, list) or not p for p in paths):
        raise ValueError("paths inválido: se espera array de arrays con UUIDs")
    return paths


def resolve_selection(payload: Dict[str, Any], *, company_id: Optional[str]) -> Dict[str, Any]:
    """
    Entradas:
      { "main":[pathIds[]...], "annex":[pathIds[]...]? }
    Salida:
      {
        ok, items, annexItems,
        commission: { perMain[], perAnnex[], combinedCapPct, globalCapPct },
        combined: { required, node, options, reason, selectedSubcategory? },
        docs: { perMain[], allMainUniform: bool }
      }
    """
    main_paths = _normalize_paths(payload.get("main") or [])
    annex_paths = _normalize_paths(payload.get(
        "annex") or []) if payload.get("annex") else []

    # 1) Validación (infiere modalidades si leaf es nm.id)
    main_validated: List[Dict[str, Any]] = []
    for path in main_paths:
        result = validate_path_and_modalidades(path, None)
        main_validated.append({"pathIds": path, "validation": result})

    annex_validated: List[Dict[str, Any]] = []
    for path in annex_paths:
        result = validate_path_and_modalidades(path, None)
        annex_validated.append({"pathIds": path, "validation": result})

    # 2) Comisión por item y mínimo (main + annex)
    main_comm = compute_commission_for_validated(main_validated)
    annex_comm = compute_commission_for_validated(
        annex_validated) if annex_validated else {"per_item": [], "cap_min": None}

    # 3) Combinado
    combined = detect_combined_requirement(
        [v["pathIds"] for v in main_validated])

    # products-backend/ramos/api/services/selection_service.py (dentro de resolve_selection)
    combined_cap = None
    if combined.get("required") and combined.get("node"):
        # Tomar min entre el L3 y sus hijos OPTION (si existen caps)
        l3_id = combined["node"]["id"]
        base = compute_commission_for_node(l3_id, None)
        # agregar candidatos OPTION hijos
        sql = "SELECT id FROM ramo.node WHERE parent_id = %s AND kind='OPTION'"
        with connection.cursor() as cur:
            cur.execute(sql, [l3_id])
            opt_ids = [str(r[0]) for r in cur.fetchall()]
        children_caps = []
        for oid in opt_ids:
            v = compute_commission_for_node(oid, None)
            if v is not None:
                children_caps.append(v)
        pool = [v for v in [base, *(children_caps or [])] if v is not None]
        combined_cap = (min(pool) if pool else None)

    # 4) Global cap = min(main_min, annex_min, combined_cap si existe)
    caps_pool = []
    if main_comm.get("cap_min") is not None:
        caps_pool.append(main_comm["cap_min"])
    if annex_comm.get("cap_min") is not None:
        caps_pool.append(annex_comm["cap_min"])
    if combined_cap is not None:
        caps_pool.append(combined_cap)
    global_cap = min(caps_pool) if caps_pool else None

    # 5) Docs (solo main) → flags por leaf real y if all uniform
    docs = list_docs_flags_for_selection(
        [v["pathIds"] for v in main_validated])

    # 6) Construcción items
    def _ramo_of(path: List[str]) -> Optional[Dict[str, Any]]:
        return _closest_ramo_in_chain(path[-1])

    # map rápido path->cap
    def _to_key(p: List[str]) -> tuple: return tuple(p)
    main_map = {_to_key(i["pathIds"])
                        : i for i in main_comm.get("per_item", [])}
    annex_map = {_to_key(i["pathIds"])
                         : i for i in annex_comm.get("per_item", [])}

    items = [{
        "pathIds": v["pathIds"],
        "ramo": _ramo_of(v["pathIds"]),
        "modalidades": v["validation"].get("modalidades"),
        "cap_percent": main_map.get(_to_key(v["pathIds"]), {}).get("percent")
    } for v in main_validated]

    annex_items = [{
        "pathIds": v["pathIds"],
        "ramo": _ramo_of(v["pathIds"]),
        "modalidades": v["validation"].get("modalidades"),
        "cap_percent": annex_map.get(_to_key(v["pathIds"]), {}).get("percent")
    } for v in annex_validated]

    return {
        "ok": True,
        "items": items,
        "annexItems": annex_items or None,
        "commission": {
            "perMain": main_comm.get("per_item", []),
            "perAnnex": annex_comm.get("per_item", []),
            "combinedCapPct": combined_cap,
            "globalCapPct": global_cap,
        },
        "combined": combined,
        "docs": {
            "perMain": docs["per_item"],
            "allMainUniform": docs["all_uniform"]
        }
    }
