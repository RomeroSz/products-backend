# security/api/views/auth.py
from django.db import connection
from django.contrib.auth import get_user_model
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from security.api.serializers.auth import SignInSerializer, RefreshSerializer, UserMeSerializer
from security.application.use_cases.resolve_user_actor import resolve_user_actor, ResolveActorError

User = get_user_model()


def _user_payload(user: User):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.get_full_name() or user.username,
        "avatar": None,
        "status": "active",
    }


class SignInView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        ser = SignInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]

        # 1) garantizar vínculo user↔actor (LOCAL)
        try:
            _ = resolve_user_actor(
                user_id=user.id,
                source="LOCAL",
                profile={
                    "display_name": user.get_full_name() or user.username,
                    "email": user.email,
                },
            )
        except ResolveActorError as e:
            return Response({"message": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # 2) (opcional) setear contexto YA en este mismo request
        try:
            with connection.cursor() as cur:
                cur.execute(
                    'SELECT "security".set_context_from_user(%s);', [user.id])
        except Exception:
            # no detengas el login por esto; el middleware lo aplicará desde el siguiente request
            pass

        # 3) emitir tokens
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token

        data = {
            "user": _user_payload(user),
            "access_token": str(access),
            "refresh_token": str(refresh),
            "expires_in": int(access.lifetime.total_seconds()),
        }
        return Response(data, status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    serializer_class = RefreshSerializer


class MeView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        ser = UserMeSerializer(request.user)
        return Response({"user": ser.data}, status=status.HTTP_200_OK)
