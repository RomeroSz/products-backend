from django.core.management.base import BaseCommand
from django.db import connection

TABLES = [
    '"security".role',
    '"security".org_area',
    '"security".actor',
    '"security".actor_role',
    '"security".user_link',
    '"security".assignment_rule',
]


class Command(BaseCommand):
    help = "Verifica existencia y conteo de tablas de security (no modifica nada)."

    def handle(self, *args, **opts):
        with connection.cursor() as cur:
            for fq in TABLES:
                try:
                    cur.execute(f"SELECT count(*) FROM {fq};")
                    count = cur.fetchone()[0]
                    self.stdout.write(self.style.SUCCESS(f"OK {fq}: {count} filas"))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"ERROR {fq}: {e}"))
        self.stdout.write(self.style.SUCCESS("Inspección terminada."))
