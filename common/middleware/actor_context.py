from django.utils.deprecation import MiddlewareMixin


class ActorContextMiddleware(MiddlewareMixin):
    header_actor = "HTTP_X_ACTOR_ID"
    header_company = "HTTP_X_COMPANY_ID"

    def process_request(self, request):
        request.actor_id = None
        request.company_id = None

        # 0) Headers de prueba (opcionales)
        aid = request.META.get(self.header_actor)
        cid = request.META.get(self.header_company)
        if aid:
            request.actor_id = aid
        if cid:
            request.company_id = cid

        # 1) Resolución real desde UserLink (si hay usuario autenticado)
        if getattr(request, "user", None) and request.user.is_authenticated:
            try:
                from security.infrastructure.models import UserLink

                link = UserLink.objects.select_related("actor").get(user=request.user)
                request.actor_id = str(link.actor_id)
                request.company_id = (
                    str(link.actor.company_id) if link.actor.company_id else None
                )
            except Exception:
                pass

        return None
