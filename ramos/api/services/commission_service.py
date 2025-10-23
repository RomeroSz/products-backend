# products-backend/ramos/api/services/commission_service.py
from typing import Any, Dict, List, Optional, Tuple
from django.db import connection
import re

from ramos.api.services.ramos_flags_service import is_vida_by_path

UUID_RX = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _ensure_uuid(s: Any) -> str:
    if not isinstance(s, str) or not UUID_RX.match(s.strip()):
        raise ValueError(f"UUID inválido: {s}")
    return s.strip()


def _fetch_nodes(ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Carga nodos por id → { id: {id, code, name, kind, parent_id} }
    """
    if not ids:
        return {}
    sql = """
    SELECT id, code, name, kind, parent_id
    FROM ramo.node
    WHERE id = ANY(%s)
    """
    with connection.cursor() as cur:
        cur.execute(sql, [ids])
        rows = cur.fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for rid, code, name, kind, parent_id in rows:
        out[str(rid)] = {
            "id": str(rid),
            "code": code,
            "name": name,
            "kind": kind,
            "parent_id": str(parent_id) if parent_id else None
        }
    return out


def _fetch_chain_up(leaf_id: str) -> List[Dict[str, Any]]:
    """
    Trae chain ascendente (leaf -> ... -> root) para un node_id.
    """
    sql = """
    WITH RECURSIVE chain AS (
      SELECT n.id, n.code, n.name, n.kind, n.parent_id, 0::int AS lvl
      FROM ramo.node n
      WHERE n.id = %s
      UNION ALL
      SELECT p.id, p.code, p.name, p.kind, p.parent_id, c.lvl + 1
      FROM ramo.node p
      JOIN chain c ON p.id = c.parent_id
    )
    SELECT id, code, name, kind, parent_id, lvl
    FROM chain
    ORDER BY lvl ASC;
    """
    with connection.cursor() as cur:
        cur.execute(sql, [leaf_id])
        rows = cur.fetchall()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "id": str(r[0]),
            "code": r[1],
            "name": r[2],
            "kind": r[3],
            "parent_id": str(r[4]) if r[4] else None,
            "level_from_leaf": r[5],
        })
    return out


def _looks_like_vida(node: Dict[str, Any]) -> bool:
    """
    Heurística ligera para ancla 'VIDA':
    - code == 'VID'
    - CATEGORY con code que empieza 'VID'
    - nombre exacto/leading 'Vida'
    """
    code = (node.get("code") or "").upper()
    name = (node.get("name") or "").strip().lower()
    kind = (node.get("kind") or "").upper()
    if code == "VID":
        return True
    if kind == "CATEGORY" and code.startswith("VID"):
        return True
    if name == "vida" or name.startswith("vida "):
        return True
    return False


def _is_vida_path(path_ids: List[str]) -> bool:
    """
    True si el path (tomando su leaf) pertenece al árbol de Vida.
    """
    if not path_ids:
        return False
    leaf_id = _ensure_uuid(path_ids[-1])
    chain = _fetch_chain_up(leaf_id)
    if not chain:
        return False
    return any(_looks_like_vida(n) for n in chain)


def _query_commission_percent_by_node(node_id: str) -> Optional[float]:
    """
    Busca MIN(FIXED_PERCENT) para ese node_id, ignorando modalidad (seguro).
    """
    sql = """
    SELECT MIN((rule_value->>'percent')::numeric) AS pct
    FROM ramo.commission_rule
    WHERE node_id = %s AND rule_type = 'FIXED_PERCENT'
    """
    with connection.cursor() as cur:
        cur.execute(sql, [node_id])
        row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def commission_percent_for_path(path_ids: List[str]) -> Dict[str, Any]:
    """
    Unidad de trabajo:
      - Valida path
      - Usa is_vida_by_path() -> si es VIDA: skip
      - Consulta % en el LEAF (último id). Si no hay, sube por la cadena (leaf→root)
        probando cada node_id hasta encontrar un FIXED_PERCENT.
    """
    if not path_ids or not isinstance(path_ids, list):
        return {"pathIds": path_ids, "percent": None, "skipped": "PATH_EMPTY"}

    # Leaf (validado)
    leaf_id = _ensure_uuid(path_ids[-1])

    # VIDA?
    try:
        is_vida, _ramo_hint = is_vida_by_path(path_ids)
    except ValueError as e:
        return {"pathIds": path_ids, "percent": None, "error": str(e)}

    if is_vida:
        return {"pathIds": path_ids, "percent": None, "skipped": "VIDA"}

    # 1) Intento en el LEAF directamente (tu caso: OPTION con regla propia)
    pct = _query_commission_percent_by_node(leaf_id)
    if isinstance(pct, (int, float)):
        return {"pathIds": path_ids, "percent": pct, "node_id": leaf_id}

    # 2) Si no hay en el leaf, subimos por el chain y probamos cada ancestro (primer match)
    chain = _fetch_chain_up(leaf_id)  # leaf -> root
    for n in chain[1:]:  # ya probamos chain[0] (leaf)
        nid = str(n["id"])
        pct_up = _query_commission_percent_by_node(nid)
        if isinstance(pct_up, (int, float)):
            return {"pathIds": path_ids, "percent": pct_up, "node_id": nid}

    # 3) No hay regla en ningún nivel
    return {"pathIds": path_ids, "percent": None}


# ---------------- NUEVO (por trayectorias) ----------------

def _normalize_paths_payload(body: Dict[str, Any]) -> Tuple[List[List[str]], List[List[str]]]:
    """
    Acepta:
      { "main": string[][], "annex": string[][] }
      o con annex como [[{pathIds:[...]}, ...], ...] (anidado)
      o con annex como [{pathIds:[...]}, ...] (simple)
    Devuelve (main_paths, annex_paths) con listas de string[].
    """
    main_raw = body.get("main") or []
    annex_raw = body.get("annex") or []

    if not isinstance(main_raw, list):
        raise ValueError("main debe ser un array de trayectorias.")
    if annex_raw is not None and not isinstance(annex_raw, list):
        raise ValueError("annex debe ser un array si se provee.")

    def to_path_list(x: Any) -> List[str]:
        """Convierte una representación de path (Lista o Dict) a List[str]."""
        if isinstance(x, list):
            # Asume que es un path (List[str])
            try:
                return [_ensure_uuid(i) for i in x]
            except (ValueError, TypeError):
                # Si falla, es porque es List[Dict] o algo inválido
                pass

        if isinstance(x, dict) and "pathIds" in x and isinstance(x["pathIds"], list):
            # Es un objeto path {pathIds: [...]}
            return [_ensure_uuid(i) for i in x["pathIds"]]

        raise ValueError(
            f"Cada trayectoria debe ser array de UUIDs o {{pathIds:[...]}}. Recibido: {str(x)[:100]}")

    # 1. Normalización de MAIN (Esta lógica estaba bien)
    main_paths: List[List[str]] = [to_path_list(item) for item in main_raw]

    # 2. Normalización de ANNEX (Lógica robusta para manejar anidamiento)
    annex_paths: List[List[str]] = []

    for item in annex_raw:
        if isinstance(item, list):
            # Puede ser un path simple (List[str]) o un grupo (List[Dict] / List[List])

            # Heurística: Si el primer elemento es un string UUID, es un path simple.
            try:
                if item and isinstance(item[0], str) and UUID_RX.match(item[0].strip()):
                    # Trata 'item' como 1 path
                    annex_paths.append(to_path_list(item))
                    continue
            except (TypeError, IndexError):
                pass  # No es un path simple de strings, o está vacío

            # Si no fue un path simple, asumimos que es un GRUPO de paths
            # (Como en tu payload: item = [ { "pathIds": [...] } ])
            for sub_item in item:
                # sub_item es la representación del path (Dict o List[str])
                try:
                    annex_paths.append(to_path_list(sub_item))
                except ValueError as e_inner:
                    raise ValueError(
                        f"Elemento anidado en annex inválido: {e_inner}")

        elif isinstance(item, dict):
            # Es un path simple en formato objeto: { "pathIds": [...] }
            annex_paths.append(to_path_list(item))

        else:
            raise ValueError(
                f"Elemento de alto nivel en annex inválido (debe ser lista o dict): {str(item)[:100]}")

    if not main_paths and not annex_paths:
        raise ValueError(
            "Debe enviar al menos una trayectoria en 'main' o 'annex'.")

    return main_paths, annex_paths


def compute_commission_from_paths(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Versión actualizada que implementa las reglas de negocio:
     - main: calcula percent por path (omitiendo VIDA). cap = MIN.
     - annex: calcula percent por path, PERO el 'cap_percent' de main
       actúa como TOPE MÁXIMO para CADA anexo individual.
    """
    main_paths, annex_paths = _normalize_paths_payload(body)

    # --- Función de evaluación (sin cambios) ---
    def eval_block(paths: List[List[str]], omit_vida: bool) -> Tuple[Optional[float], List[Dict[str, Any]]]:
        """
        Evalúa una lista de paths y devuelve el CAP (min) y los items detallados.
        'res' (resultado de commission_percent_for_path) es un dict:
        {"pathIds": ..., "percent": 0.X, "skipped": ..., "node_id": ...}
        """
        percs: List[float] = []
        items: List[Dict[str, Any]] = []
        for p in paths:
            # 1. Busca la comisión para este path específico
            res = commission_percent_for_path(p)

            # 2. Manejo de 'Vida' (si aplica)
            if omit_vida and res.get("skipped") == "VIDA":
                # Añade el item (con 'skipped') pero no cuenta para 'percs'
                items.append(res)
                continue

            # 3. Añadir el item completo (con 'percent', 'skipped', etc.)
            items.append(res)

            # 4. Acumular el porcentaje si es válido (para calcular el MIN)
            if isinstance(res.get("percent"), (int, float)):
                percs.append(float(res["percent"]))

        # 5. El CAP es el MÍNIMO de los porcentajes encontrados
        cap = min(percs) if percs else None
        return cap, items

    # --- INICIO DE LA LÓGICA PRINCIPAL ---

    # PASO 1: Evaluar MAIN primero. Este es el que define el TOPE.
    # (Regla: "El Combinado... comisión máxima será la menor de los ramos")
    main_cap, main_items_raw = eval_block(main_paths, omit_vida=True)

    # PASO 2: Evaluar ANNEX (pero aún no aplicamos el tope)
    # (Asumimos que los anexos SÍ deben calcular comisión para VIDA,
    # por eso 'omit_vida=False'. Si no, cambia a True)
    _annex_cap_temp, annex_items_raw = eval_block(
        annex_paths, omit_vida=False) if annex_paths else (None, [])

    # PASO 3: APLICAR LÓGICA DE NEGOCIO (EL TOPE DE MAIN)
    # (Regla: "En cuanto a los anexos, la comisión máxima será a lo sumo la [de las CP]")

    final_annex_items: List[Dict[str, Any]] = []
    final_annex_percs: List[float] = []

    # Solo podemos aplicar tope si main_cap es un número válido
    can_cap_annex = isinstance(main_cap, (int, float))

    for item_raw in annex_items_raw:
        # 'item_raw' es el dict devuelto por commission_percent_for_path
        # Ej: {"pathIds": [...], "percent": 0.2, "skipped": null, ...}

        original_percent = item_raw.get("percent")
        final_percent = original_percent  # Por defecto, es el original
        capped = False  # Flag para saber si aplicamos el tope

        if isinstance(original_percent, (int, float)):
            # Si el anexo tiene comisión Y podemos topearlo Y supera el tope de main...
            if can_cap_annex and original_percent > main_cap:
                # Aplicamos el tope (lo bajamos al de main)
                final_percent = main_cap
                capped = True

            # Acumulamos el porcentaje final (topeado o no)
            final_annex_percs.append(final_percent)

        # Construimos el item de respuesta final para este anexo
        final_annex_items.append({
            "pathIds": item_raw["pathIds"],
            # El porcentaje final (topeado si fue necesario)
            "percent": final_percent,
            "skipped": item_raw.get("skipped"),
            # (Opcional) Añadimos info de debug para el frontend:
            "original_percent": original_percent if capped else None,
            "capped_by_main": capped
        })

    # PASO 4: Calcular el CAP de anexos.
    # Es el MÍNIMO de los porcentajes YA TOPEADOS.
    final_annex_cap = min(final_annex_percs) if final_annex_percs else None

    # PASO 5: Respuesta final
    return {
        "ok": True,
        "main": {
            "cap_percent": main_cap,
            # Limpiamos la respuesta de main (no necesita 'original_percent' etc.)
            "items": [{"pathIds": it["pathIds"], "percent": it.get("percent"), "skipped": it.get("skipped")} for it in main_items_raw],
        },
        "annex": {
            # El cap de anexos ahora SÍ respeta el tope de main
            "cap_percent": final_annex_cap,
            "items": final_annex_items,  # Estos items ya están procesados
            "capped_by_main_percent": main_cap if can_cap_annex else None
        },
    }
# ---------------- LEGACY (si aún lo usas) ----------------


def get_commission_cap(ramo_ids, modalidad_id=None):
    """
    Compat (legacy): retorna el mínimo entre los ramos provistos.
    Ya no usamos modalidad aquí.
    """
    if not isinstance(ramo_ids, list) or not ramo_ids:
        raise ValueError("ramo_ids debe ser array no vacío.")
    ramo_ids = [_ensure_uuid(x) for x in ramo_ids]

    percs: List[float] = []
    detail: List[Dict[str, Any]] = []
    for rid in ramo_ids:
        pct = _query_commission_percent_by_node(rid)
        detail.append({"node_id": rid, "commission_percent": pct,
                      "source": "NODE_ONLY" if pct is not None else "NONE"})
        if pct is not None:
            percs.append(pct)

    return {
        "commission_cap_percent": min(percs) if percs else None,
        "per_ramo_detail": detail,
        "without_rule": [d for d in detail if d["commission_percent"] is None],
    }
