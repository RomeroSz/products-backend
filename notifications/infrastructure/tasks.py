# notifications infra tasks (stub)
# RQ jobs (stub). Puedes encolar con django_rq.get_queue("default").enqueue(fn, ...)
def send_email_notification(event_payload: dict) -> None:
    """Envia correo en base a payload (stub).
    - Resuelve destinatarios por actor/rol (cuando implementes security).
    - Usa EMAIL_* de settings; en dev imprime en consola.
    """
    # TODO: implementar adapters (plantillas) + EmailMessage/connection
    return None
