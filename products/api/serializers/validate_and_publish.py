from dataclasses import dataclass
from typing import Optional
from django.db import connection, transaction


@dataclass
class ValidateResult:
    ok: bool
    message: Optional[str]


@dataclass
class PublishResult:
    ok: bool
    version_id: str


def validate_version(version_id: str) -> ValidateResult:
    with connection.cursor() as cur:
        try:
            cur.execute(
                """SELECT core.fn_validate_before_publish(%s)""", [version_id])
            return ValidateResult(ok=True, message=None)
        except Exception as ex:
            return ValidateResult(ok=False, message=str(ex))


@transaction.atomic
def publish_version(version_id: str, vigencia_desde: str, vigencia_hasta: Optional[str]) -> PublishResult:
    with connection.cursor() as cur:
        if vigencia_hasta:
            cur.execute("""SELECT core.fn_publicar_version(%s, %s::date, %s::date)""", [
                        version_id, vigencia_desde, vigencia_hasta])
        else:
            # tu DB tiene variantes de fn_publicar_version; usamos la que recibe fechas si hay desde/hasta
            cur.execute("""SELECT core.fn_publicar_version(%s, %s::date, NULL)""", [
                        version_id, vigencia_desde])
    return PublishResult(ok=True, version_id=version_id)
