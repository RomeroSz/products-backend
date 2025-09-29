from django.db import connection
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from products.api.serializers.product_create import ProductCreateSerializer
from products.application.use_cases.create_product_bundle import (
    CreateProductInput, create_product_bundle)


class ProductCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = ProductCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = s.to_input()

        # Asegurar contexto DB (si no vino de middleware)
        with connection.cursor() as cur:
            cur.execute(
                'SELECT "security".set_context_from_user(%s)', [request.user.id]
            )

        result = create_product_bundle(CreateProductInput(**payload))
        return Response(
            {"product_id": result.product_id, "version_id": result.version_id},
            status=status.HTTP_201_CREATED,
        )
