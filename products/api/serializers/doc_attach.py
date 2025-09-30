from dataclasses import dataclass
from typing import Dict, Any, Optional
from django.db import connection, transaction


@dataclass
class AttachResult:
    link_id: str
    document_id: str
    specific_id: str
    case_id: str


def _daterange(desde: Optional[str], hasta: Optional[str]) -> str:
    if desde and hasta:
        return f'[{desde},{hasta}]'
    if desde and not hasta:
        return f'[{desde},)'
    if not desde and hasta:
        return f'(,{hasta}]'
    return '(,)'


def _insert_documento(cur, d: Dict[str, Any]) -> str:
    cur.execute("""
        INSERT INTO core.documento
            (id, nombre, tipo, mime, archivo_url, tamano, referencia_normativa, watermark, created_at, meta, hash_sha256, search_tsv)
        VALUES
            (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, %s, now(), '{}'::jsonb, NULL, NULL)
        RETURNING id
    """, [d["nombre"], d.get("tipo"), d.get("mime"), d.get("archivo_url"),
          d.get("tamano"), d.get("referencia_normativa"), d.get("watermark")])
    return cur.fetchone()[0]


def _insert_specific(cur, section: str, doc_id: str, item: Dict[str, Any]) -> str:
    if section == "CG":
        cur.execute("""
            INSERT INTO core.cg (id, documento_id, logical_code, version, idramo, estado, created_at)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, 'BORRADOR', now())
            RETURNING id
        """, [doc_id, item["logical_code"], item["version"], item["idramo"]])
    elif section == "CP":
        cur.execute("""
            INSERT INTO core.cp (id, documento_id, logical_code, version, idramo, genera_prima, estado, created_at)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, 'BORRADOR', now())
            RETURNING id
        """, [doc_id, item["logical_code"], item["version"], item["idramo"], bool(item.get("genera_prima", False))])
    elif section == "ANNEX":
        cur.execute("""
            INSERT INTO core.annex (id, documento_id, logical_code, version, idramo, genera_prima, tipo, estado, created_at)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, %s, %s, 'BORRADOR', now())
            RETURNING id
        """, [doc_id, item["logical_code"], item["version"], item["idramo"], bool(item.get("genera_prima", False)), item.get("tipo")])
    elif section == "FORMAT":
        cur.execute("""
            INSERT INTO core.format (id, documento_id, logical_code, version, tipo, estado, created_at)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s, 'BORRADOR', now())
            RETURNING id
        """, [doc_id, item["logical_code"], item["version"], item.get("tipo")])
    else:
        raise ValueError("section inválida")
    return cur.fetchone()[0]


def _insert_link(cur, section: str, vp_id: str, specific_id: str, link: Dict[str, Any]) -> str:
    vrange = _daterange(link.get("vigencia_desde"), link.get("vigencia_hasta"))
    estado = link.get("estado", "VIGENTE")
    if section == "CG":
        cur.execute("""
            INSERT INTO link.vp_to_cg (id, idversionproduct, idcg, estado, vigencia)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s::daterange)
            RETURNING id
        """, [vp_id, specific_id, estado, vrange])
    elif section == "CP":
        cur.execute("""
            INSERT INTO link.vp_to_cp (id, idversionproduct, idcp, estado, vigencia)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s::daterange)
            RETURNING id
        """, [vp_id, specific_id, estado, vrange])
    elif section == "ANNEX":
        cur.execute("""
            INSERT INTO link.vp_to_annex (id, idversionproduct, idannex, estado, vigencia)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s::daterange)
            RETURNING id
        """, [vp_id, specific_id, estado, vrange])
    else:  # FORMAT
        cur.execute("""
            INSERT INTO link.vp_to_format (id, idversionproduct, idformat, estado, vigencia)
            VALUES (uuid_generate_v4(), %s, %s, %s, %s::daterange)
            RETURNING id
        """, [vp_id, specific_id, estado, vrange])
    return cur.fetchone()[0]


def _insert_receipt(cur, case_id: str, section: str, doc_id: str, link_table: str, link_id: str, file_meta: dict):
    cur.execute("""
        INSERT INTO workflow.receipt (id, case_id, tipo, actor_id, created_at, doc_id, meta)
        VALUES (uuid_generate_v4(), %s, %s, current_setting('app.current_actor_id')::uuid, now(), %s,
                jsonb_build_object('section', %s, 'link_table', %s, 'link_id', %s, 'file', %s::jsonb))
        RETURNING id
    """, [case_id, section, doc_id, section, link_table, link_id, file_meta])


@transaction.atomic
def attach_document_to_version(
    section: str,
    product_id: str,
    version_id: str,
    document: Dict[str, Any],
    item: Dict[str, Any],
    link: Dict[str, Any],
) -> AttachResult:
    with connection.cursor() as cur:
        # asegurar product_case y abrir un case (trámite) simple para recibo
        cur.execute(
            "SELECT id FROM core.product_case WHERE product_id=%s", [product_id])
        r = cur.fetchone()
        if r:
            product_case_id = r[0]
        else:
            cur.execute("""
                INSERT INTO core.product_case (id, product_id, expediente_code, created_at, created_by_actor_id, status)
                VALUES (uuid_generate_v4(), %s, concat('EXP-', substr(uuid_generate_v4()::text,1,8)), now(),
                        current_setting('app.current_actor_id')::uuid, 'ABIERTO')
                RETURNING id
            """, [product_id])
            product_case_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO workflow.case (id, version_product_id, estado, created_at, created_by_actor_id, product_case_id, meta)
            VALUES (uuid_generate_v4(), %s, 'ABIERTO', now(), current_setting('app.current_actor_id')::uuid, %s, '{}'::jsonb)
            RETURNING id
        """, [version_id, product_case_id])
        case_id = cur.fetchone()[0]

        doc_id = _insert_documento(cur, document)
        specific_id = _insert_specific(cur, section, doc_id, item)
        link_id = _insert_link(cur, section, version_id, specific_id, link)

        link_table = {"CG": "vp_to_cg", "CP": "vp_to_cp",
                      "ANNEX": "vp_to_annex", "FORMAT": "vp_to_format"}[section]
        file_meta = {
            "name": document["nombre"],
            "mime": document.get("mime"),
            "size": document.get("tamano"),
        }
        _insert_receipt(cur, case_id, section, doc_id,
                        link_table, link_id, file_meta)

    return AttachResult(link_id=link_id, document_id=doc_id, specific_id=specific_id, case_id=case_id)
