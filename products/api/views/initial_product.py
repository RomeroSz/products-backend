from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from ..serializers.initial_product import InitialProductPayloadSer
from products.application.use_cases.create_initial_product import create_initial_product


class InitialProductCreateAPIView(APIView):
    def post(self, request, *args, **kwargs):
        ser = InitialProductPayloadSer(data=request.data)
        ser.is_valid(raise_exception=True)
        result = create_initial_product(
            payload=ser.validated_data, user=request.user)
        return Response(result, status=status.HTTP_201_CREATED)
