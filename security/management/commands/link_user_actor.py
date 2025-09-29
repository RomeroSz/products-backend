# security/management/commands/link_user_actor.py
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Vincula un user existente con un actor existente (no re-apunta si ya hay link)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--actor-id", required=True)

    def handle(self, *args, **opts):
        user = User.objects.get(username=opts["username"])
        actor_id = opts["actor_id"]
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(
                'SELECT actor_id FROM "security".user_link WHERE user_id=%s', [user.id]
            )
            row = cur.fetchone()
            if row:
                if row[0] != actor_id:
                    raise CommandError(
                        "El usuario ya está vinculado a otro actor (1:1)."
                    )
                self.stdout.write(self.style.SUCCESS("Ya estaba vinculado."))
                return
            cur.execute(
                'INSERT INTO "security".user_link (user_id, actor_id) VALUES (%s,%s)',
                [user.id, actor_id],
            )
            cur.execute('SELECT "security".set_context_from_user(%s)', [user.id])
        self.stdout.write(self.style.SUCCESS("OK, vinculado y contexto listo."))
