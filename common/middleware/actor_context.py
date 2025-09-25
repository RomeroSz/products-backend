from django.utils.deprecation import MiddlewareMixin


class ActorContextMiddleware(MiddlewareMixin):
    """
    Resuelve actor_id y company_id y los adjunta al request.

    Nota:
    - Aquí NO va lógica de negocio.
    - Inicialmente toma valores de headers para pruebas.
    - Más adelante, resolverá desde security.user_link (cuando el modelo exista).
    """

    header_actor = "HTTP_X_ACTOR_ID"
    header_company = "HTTP_X_COMPANY_ID"

    def process_request(self, request):
        # Defaults
        request.actor_id = None
        request.company_id = None

        # 1) Headers de prueba (útil en dev / herramientas)
        aid = request.META.get(self.header_actor)
        cid = request.META.get(self.header_company)
        if aid:
            request.actor_id = aid
        if cid:
            request.company_id = cid

        # 2) Futuro: resolver desde security.user_link
        # if request.user.is_authenticated:
        #     from security.infrastructure.models import UserLink
        #     try:
        #         link = UserLink.objects.select_related("actor").get(user=request.user)
        #         request.actor_id = str(link.actor_id)
        #         request.company_id = str(link.actor.company_id) if link.actor and link.actor.company_id else None
        #     except UserLink.DoesNotExist:
        #         pass

        return None
