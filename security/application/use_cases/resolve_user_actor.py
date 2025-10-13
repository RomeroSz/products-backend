# security/application/use_cases/resolve_user_actor.py
from typing import Optional, Dict, Any
from django.db import connection, transaction


class ResolveActorError(Exception):
    pass


# Política: LOCAL puede crear actor automáticamente (cámbialo a False si prefieres pre-provisión)
AUTOPROVISION_LOCAL = True
AUTOPROVISION_EXTERNAL = False  # SIGESP/SUT -> recomendado pre-provisión


def _query_one(sql: str, params: list) -> Optional[dict]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description] if cur.description else []
        row = cur.fetchone()
    if not row:
        return None
    return dict(zip(cols, row))


def resolve_user_actor(*, user_id: int, source: str = "LOCAL",
                       external_id: Optional[str] = None,
                       profile: Optional[Dict[str, Any]] = None) -> str:
    """
    Devuelve actor_id (uuid) vinculado al user_id, respetando la regla 1:1.
    Crea actor/user_link solo si está habilitada la autoprov correspondiente.
    """
    profile = profile or {}

    if source in {"SIGESP", "SUT"}:
        if not external_id:
            raise ResolveActorError(
                "external_id requerido para fuente externa")
        row = _query_one(
            'SELECT actor_id FROM "security".actor_source_ref '
            'WHERE source_system = %s AND external_id = %s;',
            [source, external_id]
        )
        if row:
            actor_id = row["actor_id"]
        else:
            if not AUTOPROVISION_EXTERNAL:
                raise ResolveActorError(
                    "Actor no pre-provisionado para fuente externa")
            actor_id = _create_actor(
                actor_type="FUNCIONARIO" if source == "FUNCIONARIO" else "SUJETO_REGULADO",
                source_system=source,
                display_name=profile.get("display_name") or profile.get(
                    "name") or f"{source}:{external_id}",
                email=profile.get("email"),
                company_id=profile.get("company_id"),
                org_area_id=profile.get("org_area_id"),
            )
            _insert_source_ref(actor_id, source, external_id, profile)

    elif source == "LOCAL":
        # 1) ¿ya linkeado?
        link = _query_one(
            'SELECT actor_id FROM "security".user_link WHERE user_id = %s;',
            [user_id]
        )
        if link:
            return link["actor_id"]

        # 2) autoprov local?
        if not AUTOPROVISION_LOCAL:
            raise ResolveActorError(
                "Usuario sin actor y autoprov LOCAL deshabilitada")

        actor_id = _create_actor(
            actor_type="FUNCIONARIO",
            source_system="LOCAL",
            display_name=profile.get("display_name") or profile.get(
                "name") or profile.get("username") or f"user:{user_id}",
            email=profile.get("email"),
            company_id=profile.get("company_id"),
            org_area_id=profile.get("org_area_id"),
        )

    else:
        raise ResolveActorError(f"Fuente desconocida: {source}")

    # 3) vincular 1:1 sin re-asignar
    existing = _query_one(
        'SELECT actor_id FROM "security".user_link WHERE user_id = %s;',
        [user_id]
    )
    if existing:
        if existing["actor_id"] != actor_id:
            raise ResolveActorError(
                "Usuario ya vinculado a otro actor (violación 1:1)")
    else:
        with connection.cursor() as cur:
            cur.execute(
                'INSERT INTO "security".user_link (user_id, actor_id, created_at) VALUES (%s, %s, NOW());',
                [user_id, actor_id]
            )

    return actor_id


@transaction.atomic
def _create_actor(*, actor_type: str, source_system: str,
                  display_name: Optional[str], email: Optional[str],
                  company_id: Optional[str] = None, org_area_id: Optional[str] = None) -> str:
    with connection.cursor() as cur:
        cur.execute('SELECT gen_random_uuid();')
        actor_id = cur.fetchone()[0]
        cur.execute(
            'INSERT INTO "security".actor (id, actor_type, source_system, display_name, email, company_id, org_area_id, created_at) '
            "VALUES (%s, %s, %s, %s, %s, %s, %s, NOW());",
            [actor_id, actor_type, source_system,
                display_name, email, company_id, org_area_id]
        )
    return str(actor_id)


def _insert_source_ref(actor_id: str, source_system: str, external_id: str, attrs: Dict[str, Any]):
    with connection.cursor() as cur:
        cur.execute(
            'INSERT INTO "security".actor_source_ref (actor_id, source_system, external_id, attrs) '
            "VALUES (%s, %s, %s, %s::jsonb);",
            [actor_id, source_system, external_id, attrs or {}]
        )
