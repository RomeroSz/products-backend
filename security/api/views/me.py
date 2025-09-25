from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "user": request.user.username,
                "actor_id": getattr(request, "actor_id", None),
                "company_id": getattr(request, "company_id", None),
            }
        )
