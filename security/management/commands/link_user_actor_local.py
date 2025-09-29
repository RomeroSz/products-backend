from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from security.application.use_cases.link_user_actor import (LinkUserActorInput,
                                                            link_user_actor)


class Command(BaseCommand):
    help = "Vincula un user existente con actor LOCAL (autoprovisiona si falta)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--actor-type", required=False, default="FUNCIONARIO")

    def handle(self, *args, **opts):
        u = User.objects.get(username=opts["username"])
        actor_id = link_user_actor(
            LinkUserActorInput(
                user=u,
                source_system="LOCAL",
                actor_type=opts["actor_type"],
                display_name=u.get_full_name() or u.username,
                email=u.email,
                attrs={"via": "link_user_actor_local"},
            )
        )
        self.stdout.write(self.style.SUCCESS(f"user={u.id} actor={actor_id}"))
