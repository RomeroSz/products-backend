# security/management/commands/create_user_with_actor.py
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from security.application.use_cases.link_user_actor import (LinkUserActorInput,
                                                            link_user_actor)


class Command(BaseCommand):
    help = "Crea un usuario Django y lo vincula 1:1 con un actor (source=LOCAL)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)
        parser.add_argument("--email", required=False, default=None)
        parser.add_argument("--display-name", required=False, default=None)
        parser.add_argument(
            "--actor-type",
            required=True,
            choices=["FUNCIONARIO", "SUJETO_REGULADO", "SERVICIO"],
        )
        parser.add_argument("--company-id", required=False, default=None)
        parser.add_argument("--org-area-id", required=False, default=None)

    def handle(self, *args, **opts):
        username = opts["username"]
        password = opts["password"]
        email = opts["email"]
        display_name = opts["display_name"] or username
        actor_type = opts["actor_type"]
        company_id = opts["company_id"]
        org_area_id = opts["org_area_id"]

        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        if created:
            user.set_password(password)
            user.save()

        actor_id = link_user_actor(
            LinkUserActorInput(
                user=user,
                source_system="LOCAL",
                actor_type=actor_type,
                display_name=display_name,
                email=email,
                company_id=company_id,
                org_area_id=org_area_id,
                attrs={"provisioned_by": "create_user_with_actor"},
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'CREATED' if created else 'EXISTING'} user={user.id} actor={actor_id} vinculados."
            )
        )
