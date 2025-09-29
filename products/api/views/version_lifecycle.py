from django.db import connection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class VersionValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, vp_id: str):
        with connection.cursor() as cur:
            cur.execute(
                'SELECT "security".set_context_from_user(%s)', [request.user.id]
            )
            # Lanza error si no está lista
            cur.execute("SELECT core.fn_validate_before_publish(%s)", [vp_id])
        return Response({"ok": True})


class VersionPublishView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, vp_id: str):
        desde = request.data.get("vigencia_desde")
        hasta = request.data.get("vigencia_hasta")
        with connection.cursor() as cur:
            cur.execute(
                'SELECT "security".set_context_from_user(%s)', [request.user.id]
            )
            cur.execute(
                "SELECT core.fn_publicar_version(%s, %s, %s)", [vp_id, desde, hasta]
            )
        return Response({"ok": True}, status=status.HTTP_200_OK)
