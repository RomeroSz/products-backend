import json
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db import connection, transaction


@dataclass
class LinkUserActorInput:
    user: User
    source_system: str  # 'SIGESP' | 'SUT' | 'LOCAL'
    actor_type: str  # 'FUNCIONARIO' | 'SUJETO_REGULADO' | 'SERVICIO'
    external_id: str | None = None  # requerido si SIGESP/SUT
    display_name: str | None = None
    email: str | None = None
    company_id: str | None = None  # UUID str
    org_area_id: str | None = None  # UUID str
    attrs: dict | None = None  # meta opcional para actor_source_ref


POLICY_ALLOW_AUTOPROVISION_LOCAL = True  # ajusta a tu política


class LinkUserActorError(Exception): ...


def link_user_actor(inp: LinkUserActorInput) -> str:
    """
    Devuelve actor_id (uuid str) ya enlazado a inp.user.
    Invariante: crea user_link solo si no existe; nunca re-apunta.
    """
    with transaction.atomic():
        with connection.cursor() as cur:
            # 1) ¿Existe ya user_link?
            cur.execute(
                'SELECT actor_id FROM "security".user_link WHERE user_id=%s',
                [inp.user.id],
            )
            row = cur.fetchone()
            if row:
                return row[0]  # Ya vinculado

            actor_id = None

            # 2) Resolver por source
            if inp.source_system in ("SIGESP", "SUT"):
                if not inp.external_id:
                    raise LinkUserActorError(
                        "external_id requerido para fuentes SIGESP/SUT"
                    )
                cur.execute(
                    'SELECT actor_id FROM "security".actor_source_ref '
                    "WHERE source_system=%s AND external_id=%s",
                    [inp.source_system, inp.external_id],
                )
                r = cur.fetchone()
                if r:
                    actor_id = r[0]
                else:
                    # En fuentes externas, lo preferible es pre-provisión; si no existe, rechaza:
                    raise LinkUserActorError(
                        "Actor no pre-provisionado para la fuente externa"
                    )
            elif inp.source_system == "LOCAL":
                if not POLICY_ALLOW_AUTOPROVISION_LOCAL:
                    raise LinkUserActorError("Autoprovisión LOCAL deshabilitada")
                # Crear actor LOCAL (actor_type válido del enum; usa FUNCIONARIO para personal interno)
                cur.execute(
                    'INSERT INTO "security".actor '
                    "(actor_type, source_system, display_name, email, company_id, org_area_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                    [
                        inp.actor_type,
                        "LOCAL",
                        inp.display_name,
                        inp.email,
                        inp.company_id,
                        inp.org_area_id,
                    ],
                )
                actor_id = cur.fetchone()[0]
                # opcional: registrar source_ref LOCAL (sin external_id) solo por trazabilidad
                cur.execute(
                    'INSERT INTO "security".actor_source_ref (actor_id, source_system, external_id, attrs) '
                    "VALUES (%s,%s,%s,%s::jsonb)",
                    [actor_id, "LOCAL", inp.user.username, json.dumps(inp.attrs or {})],
                )
            else:
                raise LinkUserActorError("source_system inválido")

            # 3) Crear user_link (1:1). Si ya existe, habría retornado arriba.
            cur.execute(
                'INSERT INTO "security".user_link (user_id, actor_id) VALUES (%s,%s)',
                [inp.user.id, actor_id],
            )

            # 4) Cargar contexto de sesión (RLS)
            cur.execute('SELECT "security".set_context_from_user(%s)', [inp.user.id])

            return actor_id
