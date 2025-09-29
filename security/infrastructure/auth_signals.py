# security/infrastructure/auth_signals.py
from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db import connection
from django.dispatch import receiver

from security.application.use_cases.link_user_actor import (LinkUserActorInput,
                                                            link_user_actor)


@receiver(user_logged_in)
def ensure_actor_and_context(sender, user: User, request, **kwargs):
    # 1) Cargar contexto de sesión (si ya existe user_link, esto basta)
    with connection.cursor() as cur:
        cur.execute('SELECT "security".set_context_from_user(%s)', [user.id])
        cur.execute('SELECT "security".get_actor_id_for_user(%s)', [user.id])
        row = cur.fetchone()

    if row and row[0]:
        return  # ya tiene actor vinculado

    # 2) (Opcional) Autoprovisión LOCAL si no existe user_link y política lo permite
    # Puedes condicionar por ruta de login o header X-Auth-Source
    source = request.headers.get("X-Auth-Source", "LOCAL")
    if source == "LOCAL":
        link_user_actor(
            LinkUserActorInput(
                user=user,
                source_system="LOCAL",
                actor_type="FUNCIONARIO",
                display_name=user.get_full_name() or user.username,
                email=user.email,
            )
        )
        # Re-cargar contexto
        with connection.cursor() as cur:
            cur.execute('SELECT "security".set_context_from_user(%s)', [user.id])
