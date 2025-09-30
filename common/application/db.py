from django.db import connection


def set_db_context_from_request(request) -> None:
    """
    Establece el contexto en la sesión de Postgres usando la función:
      security.set_context_from_user(user_id)
    Debe llamarse al inicio de cada View que haga SQL directo.
    """
    user_id = request.user.id
    with connection.cursor() as cur:
        cur.execute('SELECT "security".set_context_from_user(%s)', [user_id])
